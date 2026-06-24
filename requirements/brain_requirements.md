  # Brain (Navigation) Requirements

  | ID | Requirement | Test Method |
  |---|---|---|
  | BR-01 | Robot reaches goal within 0.15m Euclidean distance | Automated assertion per run |
  | BR-02 | Zero collisions per navigation run | Collision count assertion |
  | BR-03 | Recovery behavior completes within 10s if triggered | Timed assertion on recovery |
  | BR-04 | /robot_001/odom publishes at >= 50 Hz | Hz measurement over 10s window |
  | BR-07 | nav_success_rate >= 95% over rolling 20 runs | Drift detector |
  | BR-10 | Nav2 behavior tree returns SUCCESS | BT status assertion |
  
