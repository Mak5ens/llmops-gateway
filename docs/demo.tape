# Demo GIF of the README: `just demo-record`, with the stack up (`just gateway-up`).
# https://github.com/charmbracelet/vhs

Output docs/demo.gif

Require just
Require uv

Set Shell bash
Set FontSize 18
Set Width 1080
Set Height 560
Set Padding 20
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms

Hide
Type "clear" Enter
Show

Type "just demo"
Sleep 600ms
Enter
# The call to chat-large takes about a second on a CPU, and the trace reaches Langfuse a few seconds later.
Wait+Screen@60s /ADR-016/
Sleep 8s
