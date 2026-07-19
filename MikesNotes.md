# Session 17 — Mikes notes Ease of use, Hardening, Stabilize and plan for the future.

## User-friendliness
- Is this framework easy to install and re-use
- Is it easy for a user to kick off a run.
- Can a user config a mission? a world? add to a world? change robots? add robots or other inputs. A lot of this may not be implmented in release 1 but we don't want release 1 decsions to make things harder for future releases).
- does the README.md need updating.

## Reporting.
- how easy is it to get reports of ci sim runs?
- how easy is it to get reports from real robot runs?
- are these reports clear and show results of run and any drift detection
- are any photos taken included in the reports or have easy access links.

## Logging
- Is there enough loggind in the ci-runs to debug
- implement python logging with ability to put in debug mode.
- Need logging on the robot. easily retrievalbe. Ability to put robot in debug mode.

## Code review. 4 parts.
1) code review of latest code base.
2) code reuse. Good use of classes, best practices,
3) performance: review for long running loops etc.
4) delete unused code, 
5) review docs, consolidate and delete.
6) repeat code review, maybe with a different model.


## Drift detection and RAG/LLM
- are we using it?
- have we made any changes dueSor to observation.
- 


## Session 18 — Real Robot: Deploy + Sim-to-Real Comparison (~3 hrs)
- Not notes here. Review Session 18 later.

## Sesion 19 - Potential extra tests with current framework.
- Answer questions about physical robot startup and missions (how to reset between test. Need to physically swap balls around)
-  a camera in and test hui and other color factors on croque balls.
- New mission?
- I have the wifi module for the Nvidia. Maybe some tests with that?
- plug a camera into the Nvidia and run some tests
- Just checking, what as the "Deferred Nav2 compatibily comment we hade from Session 12, I'm guessing that is in now)
- assume the robot wake up file is done?


## FUTURE RELEASE - listing features here in no particular order - Lets decide where to put them.
- more robot autonomy
- robot wakes up and knows the mission but not where it is. -SLAM to map world?
- hardened navigation
- second robot. Cheaper bumper bot with Arduino UNO Q (combined micro processor/micro controller).  wakes up and gets all instructions from the Nvidia. The Q bumper bot may even go out and explore/map while the Nvidia robot stays in place
- have a second (maybe living room) and 3rd world (outide basketball with moveable cardboard walls)
- have a remote stationary wifi camera that the Nvidia robot can access and use to make dicsions or help map or navigate.
- make missions something the user can imput and then just run. The ci/cd pipeline should be able to handle this.
- make worlds something the user can input
- make robots something the user can just input
- the whole AMCL / real localiztion piece Session 19 or future release. Same for Recovery behaviors and Accurate footprint away planning.
- multi robot launch parameterization
- the whole nvidia cosmos 3 edge piece
- all the stuff from the blueprint that I can't think off.
- I hope to continue to learn more about robotica and in particular the software and ci. Potentially even leverageing this into a new job. But the one Important guiding principle. We want to continue to think 10x about this pipeline. Best for career prospects and truly creating something unique and needed. re-read robotics_cicd_10x_blueprint.md as a refresher.

