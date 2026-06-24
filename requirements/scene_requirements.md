  # Scene (Environment) Requirements

  | ID | Requirement | Test Method |
  |---|---|---|
  | SC-01 | World includes at least 2 obstacles placed within robot path | SDF world assertion |
  | SC-02 | Robot start position >= 2m from goal | Distance assertion at spawn |
  | SC-03 | At least 1 perturbation axis varied per test run (friction, lighting, or obstacle placement) | Perturbation matrix config check |
  | SC-04 | /robot_001/scan publishes at >= 10 Hz | Hz measurement |
  | SC-05 | /robot_001/camera/image_raw publishes at >= 10 Hz | Hz measurement 
