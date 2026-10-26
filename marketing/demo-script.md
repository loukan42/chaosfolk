# A 60-second demonstration

Record the released version after the local demo succeeds. This is a storyboard
and narration script; no video is included. Show real report screenshots and trial
files from that run. Keep a visible “local fixture” label during the application shots.

| Time | Screen | English narration |
| --- | --- | --- |
| 0–8 s | The demo project form with `Weekend project` entered | “This form clears the draft before saving. A normal test can miss what happens when the save fails.” |
| 8–18 s | Before-treatment screenshot: empty input, no saved project | “When browser storage is full, the write fails and the draft disappears.” |
| 18–30 s | Report evidence: before treatment and control | “Chaosfolk repeats the same scenario three times with the fault and three times without it. The control tells us whether the app can complete this path under normal conditions.” |
| 30–42 s | Corrected treatment screenshot and evidence | “The corrected version keeps the draft and explains the failure. The report keeps the screenshots and the result of each trial.” |
| 42–52 s | README agent prompt, clearly labelled “Exploration mode” | “For exploration, your coding agent assigns different goals and habits to simulated users. Their observations become candidates for these replays.” |
| 52–60 s | Terminal command and public repository URL | “Run the local demo without an AI key. Chaosfolk is open source, and the first version is in alpha.” |

The demo currently expects twelve valid trials: before and after, each with three
treatments and three controls. Read the generated results before stating those
counts. If the release adds another series, update the script rather than hiding
trials. The demo does not perform AI exploration, so do not put fictional user
quotes over its footage.

For a silent clip, use the narration as captions and retain the control labels.
Keep the first visible result within the opening ten seconds. Publish the full
install command in the accompanying post; do not imply that recording duration
equals first-install or test runtime.

Suggested asset names after recording:

```text
chaosfolk-demo-60s.mp4
chaosfolk-demo-captions.vtt
chaosfolk-report-desktop.png
chaosfolk-lost-draft-before-after.png
```

Record a separate end-to-end agent exploration before advertising any claim about
autonomous bug discovery. Include the host/version, number of users, action budget,
test app, measured model usage when available and which observations were reproduced.
