# Vendored JavaScript

Checked in so the page loads nothing from the network (the server can sign in the user's name, so it must not run
third-party scripts). Update by replacing the files and the line below; no build step.

| Package | Version | License | Source | File | SHA-256 |
|---|---|---|---|---|---|
| KaTeX | 0.19.1 | MIT | npm `katex` dist/ | vendor/katex/katex.min.js | fa140498b8cfc8302cbe5e7cb1bdbc1f952bc38b3fa258ede09e73edbf9a74bc |
| KaTeX | 0.19.1 | MIT | npm `katex` dist/ | vendor/katex/katex.min.css | 00e0b094171b07f58422075f469b4feac2b2f7bce1aeec943c08da4d697f4dcf |
| Alpine.js | 3.17.5 | MIT | npm `alpinejs` dist/cdn.min.js | vendor/alpine/alpine.min.js | b4036e9e9ac22fa6f6ae1ba292e015e1f3e9c85d0d79e73e4c8eb9bb139b522e |

KaTeX fonts: only the `.woff2` files are shipped (`vendor/katex/fonts/`, SHA-256 in `SHA256SUMS` there); the stylesheet also
names `.woff`/`.ttf` fallbacks for old browsers, which are not shipped. KaTeX's own license is `vendor/katex/LICENSE`;
Alpine.js is MIT-licensed (Caleb Porzio and contributors; the npm package carries no separate license file).
