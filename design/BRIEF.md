# Design brief: Study Buddy player

## Audience and the screen's single job
- **Main viewer in the demo:** an ed-tech buyer or hackathon judge watching a recording of two learners using the app.
- **Job:** show at a glance that the same lecture becomes a different experience for each learner. The player pauses at different moments, for different terms, based on what that learner already knows.
- **What the screen should make obvious without narration:**
  - whose session this is
  - how many pauses this learner gets, and how many terms were saved for the end
  - why the video stopped: the term and its explanation, plus "I already know this"
- **Secondary viewer:** the learner. The screen still has to work for a student studying for real: readable explanations, keyboard use, captions.

## Mood
Calm, focused, scholarly. A quiet library, not a dashboard. The lecture is the hero, and the app stays out of its way until it has something to say.

## References
- **Linear:** take its restraint.
  - few colours
  - a tight spacing scale
  - quiet 1px borders instead of shadows
  - crisp, visible focus rings
  - one accent colour used only for the main action
- **Readwise Reader / Kindle:** take reading typography for the term card.
  - a serif for explanations
  - a comfortable line length (about 60–70 characters)
  - generous line height
  - the term set like a headword in a dictionary

## Layout decisions already made
- **Desktop:** the video on the left, a side panel on the right with the mode switch, the pause count and the term card.
- **Phone (390 px):** one column. The term card appears directly under the video, and the page scrolls to it when the video pauses.
- **Credit:** the CS229 line (Stanford Engineering Everywhere, Andrew Ng, CC BY-NC-SA 4.0) stays visible under the video.

## Anti-references (avoid unless asked)
- purple or blue gradients
- glassmorphism
- a centred hero over three feature cards
- emoji as icons
- generic stock illustrations
- everything centred
- more than two typefaces
- unmodified shadcn defaults
- dashboard clutter: badges, charts or counters on the player beyond the single pause-count line
