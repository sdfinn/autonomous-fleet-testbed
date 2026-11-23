# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Where the RF-DETR network actually runs. One interface, two machines:

    backend.input_hw            (height, width) the network expects
    backend.infer(batch)        (1, 3, H, W) float32  ->  (boxes, logits) as numpy arrays
    backend.close()

TensorRTBackend  the Jetson's GPU. Loads a `.engine` file, which is the network compiled
                 for one exact chip and TensorRT version: it is built ON the robot from
                 the portable `.onnx` file (`trtexec --onnx=... --saveEngine=... --fp16`,
                 about three minutes) and rebuilt after a JetPack update.
OnnxRuntimeBackend  anywhere else (workstation, tests, a board with no NVIDIA GPU).
                 Loads the portable `.onnx` file directly.

Keeping the two behind one interface is deliberate (docs/detection-history.md, "Other
devices later"): the detector node is not tied to NVIDIA hardware.

Both backends import their library inside __init__, so importing this module needs
neither.
"""
import ctypes

import numpy as np

BOXES_LAST_DIM = 4


def _split_outputs(arrays):
    """(boxes, logits) from the network's two outputs, whatever order they come in:
    the boxes are the output whose last dimension is 4."""
    if len(arrays) != 2:
        raise RuntimeError('expected 2 network outputs (boxes, class scores), got %d'
                           % len(arrays))
    first, second = arrays
    if first.shape[-1] == BOXES_LAST_DIM and second.shape[-1] != BOXES_LAST_DIM:
        return first, second
    if second.shape[-1] == BOXES_LAST_DIM and first.shape[-1] != BOXES_LAST_DIM:
        return second, first
    raise RuntimeError('cannot tell boxes from class scores: output shapes %s and %s'
                       % (first.shape, second.shape))


# How many processor threads the network may use, and no spinning while they wait.
# Measured 2026-11-23 on the 32-thread workstation at the camera's 10 pictures a second:
#   ONNX Runtime's defaults   66 ms a picture, about 16 cores' worth of processor time
#   8 threads, spinning       74 ms, 7.8 cores
#   8 threads, no spinning    80 ms (worst 93 ms), 5.1 cores     <- this
#   4 threads, no spinning   117 ms: slower than the camera
# The defaults buy 14 ms for 11 cores, and in CI's simulator stage those cores are the
# ones Gazebo renders its camera and lidar on (no display there, so no graphics card).
ONNX_THREADS = 8


def onnx_session_options(onnxruntime, threads=ONNX_THREADS):
    """Session options with the thread cap above (never more threads than the machine
    has) and waiting threads that sleep instead of spinning."""
    import os
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = max(1, min(int(threads), os.cpu_count() or 1))
    options.add_session_config_entry('session.intra_op.allow_spinning', '0')
    return options


class OnnxRuntimeBackend:
    """Run the portable `.onnx` file with ONNX Runtime."""

    def __init__(self, model_path, providers=None, threads=ONNX_THREADS):
        import onnxruntime                     # not needed on the Jetson
        self._session = onnxruntime.InferenceSession(
            model_path, sess_options=onnx_session_options(onnxruntime, threads),
            providers=providers or ['CPUExecutionProvider'])
        net_in = self._session.get_inputs()[0]
        self._input_name = net_in.name
        self.input_hw = (int(net_in.shape[2]), int(net_in.shape[3]))

    def infer(self, batch):
        return _split_outputs(self._session.run(None, {self._input_name: batch}))

    def close(self):
        self._session = None


class _Cuda:
    """The four GPU-memory calls the engine needs, straight from NVIDIA's runtime
    library. The Jetson has TensorRT for Python but none of the usual helper packages
    (pycuda, cupy), and installing one for four calls is not worth a dependency."""

    HOST_TO_DEVICE, DEVICE_TO_HOST = 1, 2
    # Where JetPack puts it; not on the default library path of a non-login shell.
    FALLBACK_DIRS = ('/usr/local/cuda/lib64',)

    def __init__(self, library='libcudart.so'):
        self._lib = self._load(library)
        self._lib.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self._lib.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_size_t, ctypes.c_int]
        self._lib.cudaFree.argtypes = [ctypes.c_void_p]
        self._lib.cudaStreamCreate.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self._lib.cudaStreamSynchronize.argtypes = [ctypes.c_void_p]
        self._lib.cudaStreamDestroy.argtypes = [ctypes.c_void_p]
        for fn in (self._lib.cudaMalloc, self._lib.cudaMemcpy, self._lib.cudaFree,
                   self._lib.cudaStreamCreate, self._lib.cudaStreamSynchronize,
                   self._lib.cudaStreamDestroy):
            fn.restype = ctypes.c_int

    @classmethod
    def _load(cls, library):
        candidates = [library] + ['%s/%s' % (d, library) for d in cls.FALLBACK_DIRS]
        for candidate in candidates:
            try:
                return ctypes.CDLL(candidate)
            except OSError:
                continue
        raise RuntimeError('CUDA runtime library not found (tried %s)' % ', '.join(candidates))

    @staticmethod
    def _check(code, what):
        if code != 0:
            raise RuntimeError('CUDA %s failed with error code %d' % (what, code))

    def malloc(self, nbytes):
        pointer = ctypes.c_void_p()
        self._check(self._lib.cudaMalloc(ctypes.byref(pointer), nbytes), 'malloc')
        return pointer.value

    def to_device(self, device_ptr, array):
        self._check(self._lib.cudaMemcpy(device_ptr, array.ctypes.data, array.nbytes,
                                         self.HOST_TO_DEVICE), 'copy to GPU')

    def to_host(self, array, device_ptr):
        self._check(self._lib.cudaMemcpy(array.ctypes.data, device_ptr, array.nbytes,
                                         self.DEVICE_TO_HOST), 'copy from GPU')

    def free(self, device_ptr):
        self._lib.cudaFree(device_ptr)

    def stream_create(self):
        """A queue of GPU work of our own, so waiting for our picture does not mean
        waiting for everything else the GPU is doing."""
        stream = ctypes.c_void_p()
        self._check(self._lib.cudaStreamCreate(ctypes.byref(stream)), 'stream create')
        return stream.value

    def stream_wait(self, stream):
        self._check(self._lib.cudaStreamSynchronize(stream), 'stream wait')

    def stream_destroy(self, stream):
        self._lib.cudaStreamDestroy(stream)


class TensorRTBackend:
    """Run a TensorRT `.engine` file on the GPU (the Jetson)."""

    def __init__(self, engine_path, cuda_library='libcudart.so'):
        import tensorrt as trt                 # ships with JetPack; not on the workstation
        self._trt = trt
        self._cuda = _Cuda(cuda_library)
        self._logger = trt.Logger(trt.Logger.WARNING)
        with open(engine_path, 'rb') as handle:
            self._engine = trt.Runtime(self._logger).deserialize_cuda_engine(handle.read())
        if self._engine is None:
            raise RuntimeError(
                'could not load %s: an engine only loads on the chip and TensorRT version '
                'it was built with; rebuild it on this machine from the .onnx file'
                % engine_path)
        self._context = self._engine.create_execution_context()
        self._stream = self._cuda.stream_create()
        self._inputs, self._outputs = [], []   # (name, host array, device pointer)
        for index in range(self._engine.num_io_tensors):
            name = self._engine.get_tensor_name(index)
            shape = tuple(self._engine.get_tensor_shape(name))
            if any(dim < 0 for dim in shape):
                raise RuntimeError('tensor %s has a dynamic shape %s; export the model '
                                   'with a fixed batch of 1' % (name, shape))
            host = np.zeros(shape, dtype=trt.nptype(self._engine.get_tensor_dtype(name)))
            pointer = self._cuda.malloc(host.nbytes)
            self._context.set_tensor_address(name, pointer)
            is_input = self._engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT
            (self._inputs if is_input else self._outputs).append((name, host, pointer))
        if len(self._inputs) != 1:
            raise RuntimeError('expected 1 network input, got %d' % len(self._inputs))
        shape = self._inputs[0][1].shape
        self.input_hw = (int(shape[2]), int(shape[3]))

    def infer(self, batch):
        name, host, pointer = self._inputs[0]
        if batch.shape != host.shape:
            raise ValueError('network input must have shape %s, got %s'
                             % (host.shape, batch.shape))
        self._cuda.to_device(pointer, np.ascontiguousarray(batch, dtype=host.dtype))
        if not self._context.execute_async_v3(self._stream):
            raise RuntimeError('the engine refused to run')
        self._cuda.stream_wait(self._stream)   # the GPU has finished this picture
        results = []
        for _, out_host, out_pointer in self._outputs:
            self._cuda.to_host(out_host, out_pointer)
            results.append(out_host.astype(np.float32, copy=True))
        return _split_outputs(results)

    def close(self):
        for _, _, pointer in self._inputs + self._outputs:
            self._cuda.free(pointer)
        if self._stream is not None:
            self._cuda.stream_destroy(self._stream)
            self._stream = None
        self._inputs, self._outputs = [], []
        self._context = self._engine = None


def make_backend(kind, model_path):
    """'tensorrt' or 'onnxruntime'; 'auto' picks by the file's extension."""
    if kind == 'auto':
        kind = 'tensorrt' if model_path.endswith('.engine') else 'onnxruntime'
    if kind == 'tensorrt':
        return TensorRTBackend(model_path)
    if kind == 'onnxruntime':
        return OnnxRuntimeBackend(model_path)
    raise ValueError("backend must be 'auto', 'tensorrt' or 'onnxruntime', not %r" % kind)
