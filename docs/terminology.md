# Terminology and the goal, for both projects

The words on this page are used the same way in autonomous-fleet-testbed (AFT) and in
wayfarer (agreed with Mike, 2026-11-22). Use the full wording; do not shorten it.
American spelling.

## The goal

1. **The robot boots up and loads everything it needs.**
2. **From then on it can carry out any number of missions,** and more of them as its
   skills grow.
3. **A mission is given in one of two ways:** as a mission script with all the details,
   or, preferred, as a request in plain English to the brain.

Two example requests:

- "Take a sweep of our house and give me a rating on how much cleaning up is needed."
- "Contact the Arduino Uno Q robot, have it take a 360-degree set of photos from where
  it is, and tell me whether a skunk is visible."

In both, the robot makes the judgment, not the person.

What that takes:

- **AFT** is the real robot. Its job is to make the body and the senses trustworthy:
  reflexes, state estimation, navigation, the detector, the describer, the skills on
  real hardware, and the measured limits of that hardware.
- **Wayfarer** is where worlds, missions, skills and the brain are built and proven in
  simulation.
- The product is the brain more than the hardware: a cheap robot with a camera and a
  link can feed a more capable computer (the mother ship) that runs the brain.

## The terms

| Term | Meaning | Trained or hand-written | Makes decisions? |
|---|---|---|---|
| **Reflexes** | Safety behavior on the robot itself: the motor board stops when commands go silent; the wheels are held for an obstacle or a lost operator | Hand-written | Only stop or go |
| **State estimation** | "Where am I, and how am I moving?" The EKF blends wheel speeds and the gyro; AMCL compares the lidar scan with the map | Hand-written (standard packages) | No |
| **Navigation** | "How do I get to that pose?" Nav2's planner and controller | Hand-written (standard package) | Path and speed only |
| **Nav2's behavior tree** | The behavior tree inside Nav2: plan a path, follow it, try recoveries | Hand-written | Only how to reach one pose |
| **Detector** | Finds objects in every picture and outputs boxes with names | Hand-written today; RF-DETR (trained) next | No: it perceives |
| **Describer** | A small vision-language model (`moondream`, served by Ollama) that writes a sentence about one crop when asked | Trained | No: it answers a question |
| **Skill** | One hard-coded ability the robot can be asked to perform: go to a place, search for an object, approach it, go around it, back away, go home, take a picture | Hand-written | Only how to do that one thing |
| **Plan** | Which skill comes next, and when | Written by a person today; chosen by the brain later | This is the deciding |
| **Mission logic** | The skills together with the plan. Today it takes one of two forms: a **mission script** or **the mission's behavior tree** | Hand-written | Yes, by rules someone wrote |
| **Mission script** | Mission logic as a fixed list of steps | Hand-written | Yes, in a fixed order |
| **The mission's behavior tree** | Mission logic as a behavior tree: checks and actions that can search, retry and give up | Hand-written | Yes, by written rules |
| **Brain** | A language model, served by Ollama, that makes decisions: it chooses the plan and makes judgments | Trained | Yes |

A **behavior tree** is the general technique: task logic written as a tree of small
checks and actions. It is hand-written, not trained. There can be two in one robot, at
different levels, which is why each is always named in full:

| | AFT | Wayfarer |
|---|---|---|
| Nav2's behavior tree | Yes | Yes |
| The mission's behavior tree | No (AFT has a mission script) | Yes |

For the brain, two more distinctions:

- **Edge brain** (on the robot's own computer) and **mother-ship brain** (on a more
  capable computer, over a link).
- **Brain-assisted** (hand-written rules choose the plan and ask the brain only on
  named events, such as "unknown object" or "I am stuck"; the brain picks from a short
  fixed list of choices) and **brain-led** (the brain chooses the plan from a request
  in plain English).

## Words to avoid

- **"Model" by itself.** The detector, the describer and the brain are all models. Say
  which one.
- **"Decision tree".** That is a machine-learning term for a trained classifier.
  Neither project has one.
- **"Behavior tree" or "the tree" by itself, and short forms such as "mission tree".**
  Say "the mission's behavior tree" or "Nav2's behavior tree".
- **"Brain" for mission logic.** Mission logic is hard-coded. A brain can decide
  something nobody wrote a rule for.
- **"Autonomous" without saying what.** Today: autonomous navigation with hard-coded
  mission logic and no brain.

## How the layers stack

Bottom to top. Each layer relies on the ones under it, and a lower layer can always
refuse a higher one.

| Layer | Question it answers | How often |
|---|---|---|
| Reflexes | Must I stop right now? | Milliseconds |
| State estimation | Where am I, and how am I moving? | 10-50 times a second |
| Navigation, run by Nav2's behavior tree | How do I get to that pose? | 10-20 times a second |
| Perception: detector, describer | What is in front of me? | About 10 times a second; the describer in seconds |
| Skills | How do I do this one thing? | While the skill runs |
| Plan | Which skill next? | On events |
| Brain | What should the plan be, and what do I make of what I found? | Rarely, in seconds |

## The rule that makes a brain installable

**Goals go down, events come up.**

- A higher layer sends a goal or a choice of skill. It never sends wheel speeds.
- A lower layer reports events upward: a goal was reached or failed, a hold started or
  ended, an object was detected, an object could not be named.
- **The lower layers do not care who sent the goal.** Navigation receives a pose the
  same way from a mission script, from the mission's behavior tree, or from a brain.

The list itself, with milestones, is `docs/goals-and-events.md`.

## Why the brain does not replace the skills

- **Speed.** A language model on the robot takes seconds to answer. A reaction to a
  ball has to happen within a fraction of a second.
- **Something has to carry out the decision.** "Go around the object" must become a
  series of goals, each waited for and each able to fail. That is a skill.
- **The brain will sometimes be wrong, slow or unavailable.** Hand-written rules are
  what the robot falls back on, and a lost link must not be fatal.

So the brain takes over the **plan**, not the skills.

| Stage | Who chooses the next skill | Where |
|---|---|---|
| Mission script | A person, in a fixed order | AFT today |
| The mission's behavior tree | A person, with rules for retrying and giving up | Wayfarer today |
| Brain-assisted | The rules, except on events no rule covers, where the brain picks | The first brain |
| Brain-led | The brain, from a request in plain English | The goal |

The brain learns from the hand-written mission logic indirectly: the mission's
behavior tree writes a log of every decision, and that log is the planned training
material. A mission script stays useful at every stage, because a repeatable mission
is what tests and CI need.

## Where each project is going

Milestones M1 to M6 are defined in `docs/goals-and-events.md`.

**AFT, in order:**
1. RF-DETR replaces the hand-written detector, in shadow mode first, under the mission
   script (M1).
2. Load before go: everything is loaded and warmed before the mission starts, the
   robot reports "ready" against a checklist, and the time to ready is recorded. The
   describer is proven inside a real run and kept loaded for the whole mission (M2).
3. A box whose name is not on a short trusted list is treated as unknown; its crop goes
   to the describer and the answer is logged. A detector never says "unknown" by
   itself, so this signal has to be built. This is as far as AFT goes toward a brain
   (M3).
4. The skills run on the real robot (M4). Today turning on the spot and backing up
   fail there.

**Wayfarer:** the skills and the mission's behavior tree, then the first brain
(brain-assisted, M5), then a mission given in plain English (brain-led, M6), each
developed and proven in simulation and then installed on AFT's robot.

## Still to settle

- **The list of goals (down) and events (up)** is a draft from the AFT side;
  wayfarer's column needs wayfarer's correction.
- **Wayfarer's own documents** still use "brain" for the whole layered system; they
  need this vocabulary. That is a job for a wayfarer session.
