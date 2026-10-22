# Canvas Grades

A Catppuccin terminal dashboard for Canvas grades and submissions. See your highest attainable grade, marks needed for each grade band, and which assessments are graded, submitted or still to do.

Supports course nicknames, custom group/assessment weights, local assessments, best-N drop rules, what-if marks and offline snapshots. Changes stay local; Canvas access uses GET requests only.

## Install and run

Requires Python 3.11+. From a checkout, install with [uv](https://docs.astral.sh/uv/getting-started/installation/):

```sh
uv tool install .
canvas-grades
```

Alternatively, `pipx install .`. On Linux/macOS, `./run` sets up a local virtual environment automatically.

```sh
canvas-grades --demo     # synthetic data; no login
canvas-grades --offline  # last saved snapshot
```

## Connect

Enter your Canvas URL on first launch and choose:

- **Token:** use a personal access token if your institution allows them.
- **Cookies:** sign in in your default browser, then paste your own Cookie request header into the hidden local prompt. Press `r` to fetch directly.
- **Browser sync:** install the provided bookmark, run it on Canvas and save its export in Downloads. The TUI imports it automatically.

Choose this semester's courses when prompted. OAuth is not implemented; it requires an institution-approved developer key. [Connection steps and controls](docs/usage.md).

## Use

`r` refresh · `c` courses · `g` group weights · `a` assessment weights · `n` add custom assessment · `w` what-if · `?` help · `q` quit.

Grade bands default to A+ 89.5%, A 84.5%, A− 79.5%, then five-point steps down to D at 39.5% (D− below that). Ceilings assume full marks on ungraded work; unpublished assessments, exam hurdles and scaling can change the outcome. [Calculation details](docs/usage.md#calculations).

## Local data

Checkout runs keep settings, grades and optional credentials in gitignored `.local/`. Installed tools use the OS user-data directory (`~/.local/share/canvas-grades` on Linux). `CANVAS_GRADES_HOME` overrides the location; `CANVAS_URL` prefills the Canvas address. Existing checkout data stays where it is.

Remembered credentials are unencrypted (private `0600` files on POSIX); cookies are session-only by default. Don't share credentials or grade exports. Both Git and package builds exclude private files.

## Development

```sh
python -m pip install -e . build
python -m unittest discover -s tests
node tests/test_exporter.cjs
python -m build
```

Python tests use synthetic fixtures; Node.js is only needed to test the browser exporter. CI tests Python 3.11/3.14 and checks the installed wheel. Please use synthetic data in issues and patches.

[GPL-3.0-or-later](LICENSE). Unaffiliated with Instructure or any university.
