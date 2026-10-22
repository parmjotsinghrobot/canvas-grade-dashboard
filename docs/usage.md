# Usage and calculations

## Connecting

Enter your institution's HTTPS Canvas address (for example, `https://canvas.example.edu`). Your saved address is reused next time; `CANVAS_URL` can prefill it for a new setup.

**Token:** press `t`. Create a token under Canvas → Account → Settings → New Access Token, then enter it in the hidden prompt. Some institutions disable token creation. Uncheck **Remember token locally** for session-only use.

**Cookies:** press `k`. Sign in through your normal default browser. Open developer tools (F12) → Network, reload Canvas and select a request to your Canvas host. Under Request Headers, copy only the **Cookie** header's value and paste it into the hidden prompt. Press Connect. `r` now fetches directly. Remembering cookies is optional and off by default. If your session expires, sign in again and supply fresh cookies. The app never extracts browser profiles automatically. Whether session-authenticated API access works depends on your institution.

**Browser snapshot:** press `b`. The app opens a setup page in your default browser. Drag **Canvas Grades Sync** onto the bookmarks toolbar, open Canvas and sign in. Run the bookmark on Canvas, select courses and download the snapshot to Downloads; the TUI imports it automatically. Press `r` to open Canvas for the next sync. Press `i` to import a file saved elsewhere. The bookmark only exports grade data, never credentials. `CANVAS_GRADES_DOWNLOADS` overrides the watched directory; offline mode never watches downloads.

`CANVAS_TOKEN` and `CANVAS_COOKIE` may supply credentials through the environment; set `CANVAS_URL` too if no address has been saved. Prefer hidden prompts to avoid putting secrets in shell history. Environment credentials are not saved.

## Controls

| Key | Action |
| --- | --- |
| Tab / Shift+Tab | Move between panels |
| Arrows | Select rows and scroll tables |
| r | Open Canvas for browser sync, or fetch directly in cookie/token mode |
| c | Choose courses through browser sync, or the picker in cookie/token mode |
| b | Open default-browser login and sync bookmark setup |
| i | Import a browser snapshot saved in another folder |
| g | Edit and save custom group or assessment weights; restore Canvas defaults |
| a | Edit individual assessment weights, starting at the selected assessment |
| n | Add a custom assessment to an existing group, including an empty group |
| e | Edit the selected custom assessment's name, group, mark or completion state |
| d | Disable or enable the selected custom assessment |
| Delete | Delete the selected custom assessment (Canvas assessments cannot be deleted here) |
| w | What-if percentage on selected assessment; blank restores Canvas data |
| m | Toggle overdue, unsubmitted online assessments to zero in the scenario |
| x | Reset all what-if assumptions |
| t | Replace token |
| k | Connect using Canvas session cookies, or renew expired cookies |
| ? | Calculation notes |
| q | Quit |

The assignment table keeps four bounded columns together: **Assessment, Status, Mark, Weight**. Long titles are clipped to fit instead of pushing marks or weights off-screen. Select a row for its full name, group, due date and submission details below. Column widths adapt when the terminal is resized. The selected-course heading also shows the nickname and official name.

Statuses are **Graded** (green), **Submitted** and awaiting a grade (yellow), or **Not done** (overdue items in red). Offline assessments without submission evidence are shown as **Offline**, since Canvas cannot establish completion. A recorded zero still counts as graded. Course totals show graded, submitted-but-ungraded and not-done counts separately. Down arrows mark dropped items at the ceiling, a dash marks exclusion and an asterisk marks a local what-if override; the row details explain each one.

## Calculations

Press **g** on a course to edit its weightings. **Group weights** keep Canvas's within-group point ratios and best-N rules. **Assessment weights** let you set each assessment's percentage of the final course grade, useful when everything is in a single unweighted Canvas group; this mode replaces group/drop rules. Weights must total 100%, and 0% excludes an item. Custom weights update the ceiling, scenario and targets, are saved per Canvas host and course, and survive refreshes and restarts. Use **Restore Canvas weights** to remove an override. New groups or assessments without saved weights trigger a warning. Demo changes last only for the demo session.

You can also select an assessment and press **a** to jump to its weight in the editor (for example, give Test 2 a 15% share even if Canvas has no weighted group). The Weight column shows saved individual percentages. Before individual overrides are configured, it shows `group` or `points` to describe Canvas's calculation method. All assessment weights must total 100% when saved.

### Assessments missing from Canvas

Press **n** to add an assessment to a Canvas group with no assessment attached, such as a benchmark test group. Choose its group, enter a name and maximum points, then enter the mark if known (for example, 19 out of 20). Leave the mark blank for an ungraded assessment and choose its completion state. The entry inherits the group's weighting; it is also available in the individual-weight editor.

These rows always carry a **[custom]** tag, including when the name is clipped. Their marks and completion states come from you and are not official Canvas records. Select a custom row and press **e** to edit it, **d** to disable/enable it, or **Delete** to remove it. Disabled entries stay visible with their marks but do not contribute to grades, targets or progress counts. If disabling/removing it leaves a weighted group with no assessable points, the ceiling becomes unknown again until that group is accounted for.

Custom entries are saved per course and Canvas address in the local settings and survive restarts and fresh Canvas imports. Editing them does not change Canvas or the downloaded snapshot. Restoring Canvas weights leaves these entries intact; disable/delete them separately. Demo custom entries last only for that session. If Canvas later supplies an assessment with the same name in the same group, the app warns about possible double counting. A local entry whose group disappears is kept and flagged so you can reassign, disable or delete it. Deleting an individually weighted custom assessment removes its saved weight; redistribute the remaining percentages using **a** if necessary.

- **Canvas current:** the current score supplied by Canvas, usually a graded-work average.
- **Ceiling:** posted scores fixed (including zeros), plus 100% on unmarked assessments. A resubmission awaiting a new grade is pending even if an earlier score exists.
- **Scenario:** the same calculation with local what-if percentages and overdue policy. Nothing is written to Canvas. Scenarios last for this session.
- **Progress:** mutually exclusive graded, submitted-but-ungraded and not-done counts for visible assessments. Excused items do not count; offline items without completion evidence are listed separately in the course summary. Manually entered grades do not establish an online submission.
- **Targets:** uniform percentage needed on remaining unmarked work, recalculating drop rules each time. Required percentages round upward to two decimals. Targets use your scenario; overrides stay fixed.
- **Zero on remaining:** posted marks fixed and everything unmarked zero. Drop choices may change.

Grade bands use the built-in UoA-style cutoffs: A+ 89.5, A 84.5, A− 79.5, B+ 74.5, B 69.5, B− 64.5, C+ 59.5, C 54.5, C− 49.5, D+ 44.5, D 39.5, D− below 39.5. No intermediate whole-number rounding.

Weighted courses use group weights and points within each group; unweighted courses use total points. Items excluded from the final grade, assessments with Canvas grading type `not_graded`, and excused work do not count. Unmarked assessments remain in the ceiling calculation. Drop-lowest rules optimize the retained group's ratio rather than sorting individual percentages, respecting `never_drop`. Drop-highest minimizes the retained ratio. Combined highest/lowest rules produce a warning to compare with Canvas. Zero-point extra credit contributes when the group has regular points.

**Ceilings depend on visible Canvas data.** Unpublished exams, withheld marks, external grades, late-penalty caps, course pass requirements and scaling cannot be inferred. Overdue unmarked work is optimistically recoverable by default; use `m` or `w` to model lost marks. Posted zeros stay fixed unless overridden in the scenario. Weighted groups without assessable points and courses with multiple grading periods show unknown ceilings. Weights not totalling 100% produce a provisional figure and warning. `~` means review that course's calculation warnings.

Dates use your system timezone. The latest submission timestamp and attempt appear under the assessment table. Drop labels refer to the 100%-remaining ceiling, not necessarily the final drop choice.

## Data and access

Only authenticated **GET** requests are sent to Canvas. The browser, cookie and token clients handle pagination, refuse redirects and pagination to other hosts or outside `/api/v1/`, and retry brief rate limits. Browser snapshot sync uses same-origin requests inside your existing Canvas session. Direct cookie mode uses the Cookie header you explicitly provide and supports Canvas's prefixed JSON responses; it never sends a bearer token alongside those cookies. The app does not read browser cookies or profiles automatically. The exporter whitelists course, assessment and submission fields and downloads no credentials. Failed browser exports do not produce a partial snapshot. Downloads are validated before import, including their Canvas address and numeric marks. Failed refreshes preserve the last complete snapshot.

Checkout runs keep data in `.local/`; installed tools use your OS user-data directory (`~/.local/share/canvas-grades` on Linux). `CANVAS_GRADES_HOME` overrides either location. There is no automatic migration: to reuse checkout data in an installed tool, set that variable to the checkout's absolute `.local` path. All data stays local. On POSIX systems the directory uses mode `0700` and files use `0600`. Optional remembered tokens/cookies are unencrypted; cookie remembering is off by default. Environment credentials are never saved. Git ignores `.local/`, credential files, snapshots and downloaded exports; package builds exclude local data separately. Browser downloads outside the checkout are private too.

Browser downloads also contain your private marks. They remain in your download folder; the app does not delete them. Browser-synced course selections are remembered in the browser and in the TUI.

For an OAuth integration that can fetch directly after browser authorisation, see [OAuth notes](../OAUTH.md). A university-approved developer key is required; OAuth is not implemented yet.

API references: [nicknames](https://developerdocs.instructure.com/services/canvas/resources/users), [courses](https://developerdocs.instructure.com/services/canvas/resources/courses), [assignments](https://developerdocs.instructure.com/services/canvas/resources/assignments), [groups](https://developerdocs.instructure.com/services/canvas/resources/assignment_groups), [drop rules](https://community.instructure.com/en/kb/articles/660670-how-do-i-create-rules-for-an-assignment-group).

