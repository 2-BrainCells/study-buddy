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
Calm, focused, scholarly, but not empty. The lecture is the hero, and the page around it explains the
personalisation: whose lecture this is, where it will pause, and what it skips.

## Direction (chosen 15 Oct, revised the same day)
- **Hybrid theme:**
  - the page is light warm paper: `#F7F4EE`, ink `#1F1D1A`, white cards
  - the lecture sits in a full-width dark band (`#0F1115`), like theatre mode
  - the term card is a white paper card on that dark band
- **Status colours, used the same way everywhere:**
  - amber `#E3B341`: pauses
  - grey: terms saved for the end
  - teal (`#1F7A68` on light, `#5EC2B0` on dark): terms skipped because the learner already knows them
- **Fonts:** Inter for the UI; Newsreader for headwords, explanations and headings.
- **Magnitudes use neutral ink**, with one exception: the dashboard's lecture strip uses amber for learner activity, because amber already means "paused" everywhere else in the product.
- **History:** the first version (Direction B, all dark and very sparse) passed the design critic. You found it too dark and too minimal, so the light page and the added content replaced it.

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
- **Profile strip** above the band:
  - initials and name
  - "Comfortable with ..." and the number of note terms
  - the pause, skipped and saved counts
- **Desktop band:** the video, with the pause timeline and a legend, on the left. A side panel on the right holds the mode switch and the term card; when no card is showing, a short "what happens here" note takes its place.
- **Below the band**, two lists:
  - "This lecture for <learner>": every stop, with its state, which you can click to jump to it
  - "Skipped for <learner>": known terms with the reason
- **Setup:** a one-line pitch, learner cards with a profile summary, and the "Add a learner" form.
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
