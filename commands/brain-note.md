# brain-note

Leave a quick note for another agent without going through /brain-done.
Use mid-work when you discover something the other agent needs to know.

Usage: `/brain-note gemini AUTH-01 JWT tokens need rotation`

## Steps

Parse `$ARGUMENTS` as: `<agent> <topic> <rest of message>`
- First word = agent (`gemini` or `claude`)
- Second word = topic (ticket ID or keyword)
- Everything after = message text

Call: `leave_note(agent, topic, message, "claude")`

Confirm: "Note left for [agent] — topic: [topic]"

If `$ARGUMENTS` has fewer than 3 words, respond:
"Usage: /brain-note <agent> <topic> <message>"
