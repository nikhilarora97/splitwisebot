# Receipt Relay

A personal receipt-to-Splitwise app: upload a receipt, type or dictate who had what, review exact shares, and add the expense to your own Splitwise account.

Features include item-by-item assignments, proportional tax/tip/discount allocation, exact cent rounding, receipt-total checks, and duplicate-post safeguards. No credentials, receipt photos, or personal history are included in this repository.

## Setup

Requirements: Python 3.11+, a Splitwise API key, and internet access for Splitwise. Local photo scanning requires macOS with Swift. ChatGPT interpretation requires the Codex CLI signed in with an eligible ChatGPT account. The optional OpenAI API reader can also run on other platforms.

From the cloned repository directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
sh run.sh
```

Open [http://localhost:8010](http://localhost:8010). Keep the app running while you use it. Run `sh run.sh` again to restart it later. The app listens on this computer only; this link does not provide phone or public access. On Windows, use `.venv\Scripts\python` and run `-m uvicorn splitwise_receipts.server:app --host 127.0.0.1 --port 8010` instead of the shell launcher.

## Connect your own accounts

1. Sign in at [Splitwise apps](https://secure.splitwise.com/apps), register a personal app, and use `http://localhost:8010` for its website. This project uses a personal API key, not an OAuth callback.
2. Generate the app’s **API key**, which is different from its consumer key and consumer secret.
3. In Receipt Relay, open **Settings**, enter that API key, and save. Your friends, groups, and currencies will load.

Every person running this project must connect their own accounts.

### Receipt readers

| Reader | Requirements | Behavior |
| --- | --- | --- |
| **ChatGPT sign-in · no API key** | Codex CLI signed in with ChatGPT | Interprets photos and natural-language instructions using your plan access. |
| **Local scanner · manual assignments** | macOS and Swift | Scans on your Mac; assign people to items manually. |
| **OpenAI API · separate key** | Your OpenAI API key and API billing | Uses the Responses API to interpret the receipt. |

For ChatGPT mode, install the [official Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli), run `codex login` and choose ChatGPT, then refresh the app. Codex is detected from PATH or the ChatGPT Mac app bundle. The helper runs locally, but AI processing happens online at OpenAI and uses your account’s access and limits. It is not an offline model. Browser cookies are not extracted or reused.

For API mode, add an OpenAI API key in Settings. API billing is separate from ChatGPT. Copy `splitwise_receipts/.env.example` to `splitwise_receipts/.env` to configure credentials through the environment or change `OPENAI_MODEL`.

The local scanner tries the Swift interpreter. You can optionally compile it on your Mac:

```sh
mkdir -p splitwise_receipts/private
swiftc -module-cache-path /tmp/receipt-relay-swift-cache \
  splitwise_receipts/ocr.swift -o splitwise_receipts/private/receipt-ocr
```

Swift is included with Apple’s command-line developer tools. Local OCR handles simple item/price rows; always review its transcription. Paste receipt text if scanning is unavailable.

## Use

1. Choose a Splitwise group or individual friends. Include the payer.
2. Upload a JPEG/PNG photo (up to 10 MB), paste receipt text, or describe priced items in the instructions field using ChatGPT/API mode.
3. Type or dictate instructions such as “I had the burger, Alex had the salad, and everyone shared fries.” Without a photo, include explicit prices: “My burger was $18, Alex’s salad was $14, and the three of us shared $9 fries. Tax was $4.10, tip $8.20, and total $53.30.”
4. Click **Read receipt**. Review items, line totals including quantity, assignments, currency, payer, date, tax, tip, discount, and the receipt final total.
5. Click **Review split**. Resolve any total mismatch, then click **Add expense to Splitwise**.

**Dictate instructions** uses browser speech recognition where supported and may use the browser/vendor’s speech service. Microphone access requires your permission. Otherwise use keyboard dictation in the instructions field or type.

The local scanner does not apply natural-language instructions; assign people using the item chips. **Try an example** works without credentials and cannot post until Splitwise is connected.

## Calculation and limits

Items split equally among assigned people. Tax, tip/service charges, and discounts are proportional to item shares. Integer-cent arithmetic and largest-remainder allocation keep totals exact; participant order breaks fractional-cent ties. A supplied final receipt total must match before posting.

One payer and amounts with two decimal places are supported. Weighted item splits, multiple payers, attaching the receipt image to Splitwise, public hosting, and multi-user accounts are not implemented. Review ambiguous AI assignments and unclear prices manually.

## Privacy and operations

This is a single-user local tool without application user authentication. Keep it bound to loopback as configured; do not expose it directly to the public internet. Host/origin protections, request-size limits, and a restrictive content security policy are included.

Keys saved in Settings live in `splitwise_receipts/private/credentials.json`, restricted to the OS user (0600) in a private directory (0700). They are not encrypted at rest and are never returned to the browser. Removing saved keys does not remove credentials configured in `.env`.

Local scans stay on your computer and receipt image files are temporary. ChatGPT/API readers send submitted receipt data, instructions, selected names/IDs, and default currency to OpenAI. API mode uses `store: false`; provider retention policies still apply. Posting sends itemized notes and paid/owed shares to Splitwise under its policies and may notify other members. Splitwise may collect API usage information.

ChatGPT mode invokes supported `codex exec` in a temporary directory with read-only sandboxing, command tools/browsing/connectors/hooks disabled for that invocation, and user configuration ignored. App secrets are excluded from the child environment. Output is schema-constrained and validated. It uses `--ephemeral` and disabled history; normal provider/platform operational retention may still apply. Calls are serial and time out after three minutes. Temporary receipt/output files are deleted. The helper cannot post expenses through this workflow.

Local preview and posting history lives in `splitwise_receipts/private/receipts.sqlite3`. The same account and exact draft reuse a preview and cannot post twice. Uncertain creation responses block automatic retries. Check Splitwise before changing the draft and trying again: changed drafts use different duplicate keys. This is a local safeguard, not a Splitwise idempotency guarantee.

To remove local history, stop the app and delete that SQLite file. This also removes duplicate safeguards and does not delete posted expenses. Correct/delete those directly in Splitwise.

**Never commit or share `.env`, the `private/` directory, or screenshots containing personal account data.** These are excluded by `.gitignore`.

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -v
```

23 tests cover arithmetic (including 2,000 randomized allocation cases), assignment validation, total reconciliation, text parsing, request protections, secret handling, account isolation, duplicate/uncertain submissions, ChatGPT routing, temporary cleanup, and secret-free helper environments. External inference and Splitwise writes are mocked; the suite creates no real expenses.

GitHub Actions runs tests on Python 3.11 and 3.13. Actual OCR requires macOS; live inference/posting requires each user’s own credentials and review.

## Usage terms and references

Intended for personal use. Review [Splitwise’s API terms](https://dev.splitwise.com/) before distributing an integration or using it commercially. Each user is responsible for their provider accounts and terms.

[Codex authentication](https://learn.chatgpt.com/docs/auth) · [Codex CLI](https://learn.chatgpt.com/docs/developer-commands?surface=cli) · [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
