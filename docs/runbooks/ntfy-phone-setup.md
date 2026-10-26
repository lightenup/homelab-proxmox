# ntfy Phone Setup

Set up the ntfy Android app to receive push notifications from the self-hosted ntfy server
(spec `082`, FR-015).

## Prerequisites

- ntfy is deployed and reachable at `https://ntfy.hus-sky.no` (LAN or tailnet).
- The owner's password is in the password manager (entered at `ansible-vault edit` time,
  never stored in this repo).
- Tailscale is installed on the phone (for away-from-home delivery).

## Install the app

1. Install **ntfy** from the [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
   or [F-Droid](https://f-droid.org/packages/io.heckel.ntfy/).

## Add the server

1. Open the app.
2. **Settings** → **Default server** → enter `https://ntfy.hus-sky.no`.
3. **Settings** → **Manage users** → **Add user**:
   - Username: `owner`
   - Password: from the password manager.
4. Verify the user is saved (it will appear in the user list).

## Subscribe to topics

1. Tap the **+** button (or long-press the subscription list).
2. Subscribe to `alerts` (Alertmanager notifications).
3. Subscribe to `hermes` (Hermes Agent scheduled jobs and chat replies, specs `083`/`095`).
4. Subscribe to `hermes-in` and **mute it** (topic menu → notifications off). This is where
   you type to Hermes (spec `095`); your own messages need no alert.
5. (`095` P2, once the action relay is deployed) Subscribe to `relay` for button
   confirmations.
6. For each topic, confirm **"Instant delivery"** is toggled on.
5. **Settings** → **Connection protocol** → **WebSockets** (the app offers this; lighter on
   battery than the default JSON stream). Caddy proxies WebSockets without extra config;
   verified 2026-10-17 at 7 s on mobile data.

## Notification channel (optional)

To make critical alerts break through Do Not Disturb:

1. **Settings** → **Notifications** → select the `alerts` topic.
2. Set the notification channel to **Urgent** (or the highest available importance).
3. In Android **Settings** → **Apps** → **ntfy** → **Notifications** → select the channel →
   enable **"Interrupt Do Not Disturb"**.

## Battery optimisation (required for reliable delivery)

Android's battery saver can kill the persistent connection. Disable it for ntfy:

1. Android **Settings** → **Apps** → **ntfy** → **Battery**.
2. Set to **Unrestricted**.

Alternatively: **Settings** → **Apps** → **Special access** → **Battery optimization** →
**ntfy** → **Don't optimize**.

## Tailscale (away-from-home delivery)

1. Install [Tailscale](https://tailscale.com/download/android) if not already present.
2. Log in with the estate's Tailscale account.
3. **Settings** → **Always-on VPN** → enable.

With Always-on VPN, the phone stays on the tailnet even when Wi-Fi is off, so ntfy's
persistent connection survives mobile-data transitions.

## Verifying reach

Open a browser on the phone (LAN or tailnet) and navigate to:

```
https://ntfy.hus-sky.no/v1/health
```

Expected: `{"healthy":true}`.

## What a 72-hour gap means (FR-013)

ntfy caches messages for **72 hours** after they are published. If the phone is unreachable
for less than 72 hours, it receives all cached messages on reconnect. If the phone is
unreachable for more than 72 hours, older messages are deleted by design and will not be
delivered. This is not a bug — it is the configured retention window (`cache-duration: "72h"`).

## Chatting with Hermes (spec `095`)

- **Type on `hermes-in`; read replies on `hermes`.** Typing in the `hermes` topic fails with
  "The user "owner" is not authorized": only the agent writes there. The ntfy web app
  (`https://ntfy.hus-sky.no` in a browser, signed in as `owner`) works the same way, and two
  windows side by side make the conversation easy to follow.
- **Long replies arrive in parts** marked `(1/2)`, `(2/2)`. The app lists the newest first, so
  read from the bottom up.
- **If Hermes asked you a question, your next message is taken as the answer**, even if you
  typed `/new` in between. Answer the question first.
- **Hermes may push back on destructive requests** ("what did you mean?") before it even asks for
  approval. Say plainly what the target is and why. The approval prompt is still the real control.
- **Messages sent while Hermes is offline are lost.** On every restart Hermes posts a silent
  notice naming the window ("Anything sent to hermes-in between 11:45 and 12:00 was not
  received"). A longer outage raises the `HermesNtfyStreamDown` alert.
- **If the AI model is unavailable** (the Mac is asleep or away), Hermes replies that your request
  was not processed. Send it again later.

## Approving from the phone (spec `095` FR-004)

When Hermes wants to run a flagged command it posts "⚠️ Hermes wants to run a command that needs
your OK" with the command and the reason. **Read the command before answering.** Answer on
`hermes-in`:

| You send | Effect |
|---|---|
| `/approve` (or `yes`, `ok`, 👍) | Runs this command once. |
| `/approve session` | Runs it, and allows that **kind** of command (e.g. any recursive delete) until `/new` or `/reset`. Other flagged commands still ask. |
| `/deny` (or `no`, 👎) | Not run. Hermes is told not to retry. |
| no answer within 15 minutes | Not run. |
| **`/approve always`** | **Do not use.** Allows the pattern permanently, for scheduled jobs too, until the agent restarts. It triggers the `HermesPermanentApprovalGranted` alert. If it happens, revoke it on the hermes LXC with `docker restart hermes_agent`. Replying `always` or `remember` has the same effect. |

- **Type the scope word bare.** `/approve always.` with a trailing full stop is read as a one-time
  `/approve`. Phone autocorrect adds full stops, so check before sending.
- Only one prompt is pending at a time. If you asked for two flagged commands, the second prompt
  appears after you answer the first.

## Commands you can type (spec `095` FR-014)

`/help` in the app shows the same list. Anything else (`/yolo`, `/update`, …) is refused with
"admin-only here".

| Command | Does |
|---|---|
| `/new` (`/reset`) | Start a fresh conversation; ends any `/approve session` |
| `/approve`, `/deny` | Answer a pending prompt (above) |
| `/cancel` | Decline a confirmation (`/undo` and `/new` ask "approve or cancel?") |
| `/stop` | Stop what Hermes is doing |
| `/status` | Session, model and context info |
| `/retry` | Re-send your last message |
| `/undo` | Drop the last exchange (asks to confirm) |
| `/compress` | Shorten a long conversation |
| `/usage` | Token use for this conversation |
| `/title <name>` | Name the conversation |
| `/model` | Show the model alias |
| `/help`, `/whoami` | The list above; your access level |

## Phone lost / revoke access (spec `095` FR-010, SC-006)

The app signs in as `owner` with the **password**, and the vault also holds an owner **token**.
Whoever holds either can type to Hermes (`hermes-in`), so treat both as shell credentials.

1. Generate a new password hash and a new token (commands in
   `docs/runbooks/ntfy-add-publisher.md` § 2).
2. `ansible-vault edit ansible/group_vars/services/vault.yml`: replace `ntfy_owner_password_hash`
   and `ntfy_owner_token`.
3. Deploy `ntfy` once (Prod 1 → Prod 2).
4. Check that both old credentials are refused, as in quickstart § 6 of `specs/095-ntfy-two-way`:
   `curl -u owner:<old password>` and `curl -H "Authorization: Bearer <old token>"` against
   `POST https://ntfy.hus-sky.no/hermes-in` both return 403.
5. Sign the new phone in with the new password.

## Troubleshooting

| Symptom | Check |
|---|---|
| No notifications at all | Is the app in the foreground at least once after install? Android may not start the service until the user opens the app. |
| Notifications delayed by minutes | Battery optimisation not set to Unrestricted. |
| No notifications away from home | Tailscale not connected, or Always-on VPN not enabled. |
| `{"healthy":false}` from `/v1/health` | ntfy container is down — check the LXC. |
| "The user "owner" is not authorized" when replying to Hermes | You typed in `hermes`; type in `hermes-in`. |
| Hermes ignores your message | It was taken as the answer to a pending question, or Hermes was offline (look for the gap notice). |
| A command ran without asking | Plain single-file deletes in Hermes's own data folder are not flagged upstream (`095` research R-014). |
