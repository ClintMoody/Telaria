# Bundled fonts — attribution & license

Talaria's wizard ships two typefaces locally (never from a CDN) so the GUI stays
fully self-contained and works on an offline machine. Both are free/open fonts under
the **SIL Open Font License, Version 1.1** (OFL-1.1), whose terms permit bundling and
redistribution — including as subsets — provided this notice travels with them.

| File | Family | Upstream | License | Copyright |
|------|--------|----------|---------|-----------|
| `Inter-400/500/600/700.woff2` | Inter | https://github.com/rsms/inter | OFL-1.1 | © The Inter Project Authors |
| `JetBrainsMono-400/700.woff2` | JetBrains Mono | https://github.com/JetBrains/JetBrainsMono | OFL-1.1 | © The JetBrains Mono Project Authors |
| `Collapse-Regular/Bold.woff2` | Collapse | https://github.com/NousResearch/hermes-agent | MIT | © 2025 Nous Research |

These `.woff2` files are **subsets** of the upstream fonts (Latin text plus the handful
of UI symbols the wizard draws), reduced only to keep the bundle small. No glyphs were
redrawn and the fonts were not renamed; they remain the original works under their
respective licenses.

**Collapse** is the Nous Research brand display face, used here — bold, uppercase,
wide-tracked — to echo the Hermes Agent wordmark, exactly as the Hermes desktop app
uses it. It ships inside the MIT-licensed `NousResearch/hermes-agent` repository; the
MIT license expressly permits redistribution provided its notice travels with the file:

> MIT License — Copyright (c) 2025 Nous Research. Permission is hereby granted, free of
> charge, to any person obtaining a copy of this software … to deal in the Software
> without restriction, including … the rights to use, copy, modify, merge, publish,
> distribute … The above copyright notice and this permission notice shall be included
> in all copies … THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

Talaria is a community tool and is **not affiliated with or endorsed by Nous Research**;
the Collapse face is used only to visually match the Hermes ecosystem, not to imply any
official relationship.

## SIL Open Font License, Version 1.1 — summary of terms

The full license text is available from each upstream project (the `OFL.txt` in the
repositories above) and at https://openfontlicense.org. In brief, OFL-1.1 grants the
right to use, study, copy, merge, embed, modify, and redistribute the fonts, subject to:

1. Neither the fonts nor any derivative may be sold on their own.
2. Bundled or redistributed copies must carry this license and copyright notice.
3. Derivatives must not use the Reserved Font Names ("Inter", "JetBrains Mono") without
   permission — the files here are unmodified-outline subsets and keep the original names.
4. The fonts are provided "as is", without warranty of any kind.

Talaria itself is MIT-licensed (see the repository `LICENSE`); that license covers the
software, while these font files remain under OFL-1.1 as noted here.
