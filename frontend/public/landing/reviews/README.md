# Student portraits

Avatars for the `STUDENT_REVIEWS` array in `frontend/src/LandingPage.jsx`.
Set `photo: 'file-name.jpg'` on an entry and drop the file here.

Requirements:

- Square (1:1), 200×200 or larger. Then run `node scripts/optimize-images.mjs`
  from `frontend/` (add the file name to its portrait list): it resizes to a
  112 px short side for the 52 px avatar, and CI fails above 16 KB.
- The student's own photograph, supplied with the **same written consent as the
  quote**. A stock or generated face attached to a testimonial invents a person
  who then appears to endorse the product; that is not a placeholder, it is a
  fabricated review.

While `photo` is an empty string the avatar shows the student's initials, which
is why every sample entry currently leaves it blank. Add a photo and a quote
together, never a photo on its own.
