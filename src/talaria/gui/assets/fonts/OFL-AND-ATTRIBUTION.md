# Bundled fonts — attribution & license

Talaria's wizard ships two typefaces locally (never from a CDN) so the GUI stays
fully self-contained and works on an offline machine. Both are free/open fonts under
the **SIL Open Font License, Version 1.1** (OFL-1.1), whose terms permit bundling and
redistribution — including as subsets — provided this notice travels with them.

| File | Family | Upstream | Copyright |
|------|--------|----------|-----------|
| `Inter-400/500/600/700.woff2` | Inter | https://github.com/rsms/inter | © The Inter Project Authors |
| `JetBrainsMono-400/700.woff2` | JetBrains Mono | https://github.com/JetBrains/JetBrainsMono | © The JetBrains Mono Project Authors |

These `.woff2` files are **subsets** of the upstream fonts (Latin text plus the handful
of UI symbols the wizard draws), reduced only to keep the bundle small. No glyphs were
redrawn and the fonts were not renamed; they remain the original works under OFL-1.1.

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
