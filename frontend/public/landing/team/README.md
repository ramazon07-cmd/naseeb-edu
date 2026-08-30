# Team portraits

Portraits for the `TEAM` array in `frontend/src/LandingPage.jsx`.

The landing page renders a **circular** portrait, so supply a **square** image
with the face centred — anything else gets cropped at the edges by
`object-fit: cover`.

| Person | Set `photo` to | Expected file |
| --- | --- | --- |
| Humoyun Nasipkulov | `'humoyun.jpg'` | `humoyun.jpg` |
| Sevinchkhon Amanova | `'sevinchkhon.jpg'` | `sevinchkhon.jpg` |
| Firdavs Juraev | `'firdavs.jpg'` | `firdavs.jpg` |
| Asadbek Ismoilov | `'asadbek.jpg'` | `asadbek.jpg` |
| Shakhriyor Pulatov | `'shakhriyor.jpg'` | `shakhriyor.jpg` |

Requirements:

- Square (1:1). 480×480 or larger, so the 168px slot stays sharp on a 2x screen.
- JPEG or WebP, under ~150 KB each. These load on the public landing page.
- The person's own photograph, used with their agreement. Never a stock or
  generated portrait — this band is a factual claim about who builds Naseeb Edu.

While `photo` is an empty string the entry renders its initials monogram
instead. That is a designed state, not a placeholder to be rushed: a missing
photograph never breaks the row, so add each one as it arrives.
