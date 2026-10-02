# Breeder review: start here

Allow about **10-15 minutes**. This is practice with synthetic data, so use a hypothetical decision.

## Open the app

1. In the main application folder, double-click **Start-Breeder-Review.cmd**. Windows may show the name as **Start-Breeder-Review**.
2. Wait for the browser to open. Leave the black command window open while reviewing.
3. Your practice decisions are kept in a separate session. Each launch starts fresh and keeps a review report; it does not change the team's records.

If your browser does not open, copy the address beginning `http://127.0.0.1:` from the black window into your browser. If the window says uv is missing or reports an installation error, ask the team to complete setup using [team setup](../SHARE.md).

## What to try

1. Find **SYN-MZ-00001** using the candidate search and click its row. In **Evidence**, inspect why the system suggests AMBER and open one source. Note anything unclear.
2. Open **Decision**. Enter your name or initials, choose **HOLD**, and enter a practice reason such as "Hold pending another usable trial and review of moisture." Choose **Review decision**, read the summary, then **Record decision** once.
3. Open **History**, then return to **Decision**. You should see your saved decision. Refresh the browser, find the same candidate again and check that history still has one decision. Open its original evidence.
4. Choose **Record another decision**. The new choice and reason should be blank. Record a second deliberate practice decision with a different reason. History should now contain exactly two decisions, with your latest decision shown last.
5. In **Ask**, enter "Why is this candidate AMBER? Cite the evidence." Read the answer, expand **More detail** if shown, and open one source. Note whether the explanation and navigation make sense. If Ask is unavailable, tell the team and continue reviewing the evidence manually.

Please note which steps you completed, where you needed help, any confusing wording and any unexpected extra decisions. There is no need to measure time unless your team has asked you to. The app's recommendations remain provisional, and this review does not validate crop thresholds.

If Ask says it is unavailable, continue with the Evidence, Decision and History steps and note that the AI step was unavailable. Wait for the current request to finish before retrying. The model service can fail even while the rest of the app works. Refreshing the browser loads app updates and keeps recorded practice decisions in the same session; copy any unsaved text first.

## Finish

Return to the black command window and press **Enter** when finished. This closes the practice session and saves its report. Close the browser tab afterwards. Reports and separate practice storage are kept in `app/data/reviews/`. Share your observations and the report location printed next to **Evidence:** with the team. Your notes are the human feedback; the app does not measure comprehension for you.

For everyday use after the review, **Start-Dashboard.cmd** opens the normal app and its ongoing decision history.
