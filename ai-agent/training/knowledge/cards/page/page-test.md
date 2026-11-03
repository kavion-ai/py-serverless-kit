# Studio: Test

How to open: Left navigation label Test. Test on a function row opens the same page with that function selected.

What it is for: Send an event at a function. docs/studio.md#test-functions says you pick a trigger or Direct invoke, edit a payload, then run locally or send to the deployed function.

What you see: Section "1. Choose the event". Each trigger is a card. A trigger index below zero is labeled Direct invoke and "no trigger". Section "2. Edit the event". HTTP shows Request, with help "Path with query string, e.g. /items/42?verbose=1. Path parameters ({id}) need real values." Other bodies use Payload (JSON). GET and HEAD hide the payload field. Saved events help says they are kept in `.pskit/studio/test-events.json`. There is a sample chip and a Save event button. Section "3. Run it" has "▶ Run locally" (title "Runs the handler on this machine with a synthetic event") and "☁ Send to <provider> / <stage>". A toggle is labeled "Show the function's logs". Section "How to test this", hint "studio, terminal or cloud console".

What you can do: Run locally is the studio form of `pskit invoke`. Send to the provider and stage is the studio form of `pskit trigger`. The send button is disabled when `trigger.remote.supported` is false, and the title then shows `trigger.remote.reason`. docs/studio.md says a storage sample matches the trigger prefix and suffix, and a schedule sample uses the trigger's own input. How to test this shows studio steps, terminal commands (local `pskit invoke`, deployed `pskit trigger`, and the cloud CLI) with Copy, and cloud-console steps.

Tips and limits: Run locally does not deploy and does not call the cloud. Send does, and it needs a deployed function whose trigger pskit can fire. On premises, section 3 also shows a Server picker when the function is deployed. Saved events are per project file, not per cloud account.

Sources: `dashboard-ui/src/studio/views/Test.tsx`, `docs/studio.md#test-functions`
