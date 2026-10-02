"""Extra cases for the `next` / `last_ok` labels, plus derivation of those labels for the original cases.

next    = the correct next step: continue | retry | replan | ask_user | done
last_ok = 1 if the last action had its intended effect on screen
All labels are the assistant's own judgement (no independent annotator).
"""


def extend(rows, add, W, L):
    def X(group, nxt, ok, *a):
        add(group, *a, 0, 0)
        rows[-1].update(next=nxt, last_ok=ok)

    D = lambda *a: X("D", "done", 1, *a)
    D(W, "Create a folder named Reports on the Desktop", ["right-click Desktop", "click New > Folder", "type Reports", "press Enter"], "press Enter",
      "Desktop | Reports (folder) | Recycle Bin | Microsoft Edge", "page changed")
    D(L, "Create the file notes.txt", ["open terminal", "type touch notes.txt", "type ls"], "type ls",
      "$ touch notes.txt\n$ ls\nnotes.txt\n$ _", "terminal output appeared")
    D(W, "Set the wallpaper to the blue image", ["open Settings", "click Personalization", "click Background", "choose blue-waves.jpg"], "choose blue-waves.jpg",
      "Settings > Personalization > Background | Current background: blue-waves.jpg (applied) | Preview shows the blue wallpaper", "page changed")
    D(W, "Download the invoice PDF", ["open billing page", "click Download invoice"], "click Download invoice",
      'Downloads | invoice-0912.pdf | Download complete | Link "Show in folder"', "page changed")
    D(W, "Rename draft.docx to final.docx", ["select draft.docx", "press F2", "type final.docx", "press Enter"], "press Enter",
      "Explorer | final.docx | notes.txt | budget.xlsx", "page changed")
    D(L, "Install curl", ["open terminal", "type sudo apt install curl", "enter password"], "enter password",
      "Setting up curl (8.5.0) ...\nProcessing triggers for man-db ...\n$ curl --version\ncurl 8.5.0 (x86_64-pc-linux-gnu)\n$ _", "terminal output appeared")
    D(W, "Send Bob the file", ["open Outlook", "attach file", "type recipient", "click Send"], "click Send",
      "Outlook | Sent Items | Message sent: 'Budget attached' to bob@company.com | Inbox (3)", "page changed")

    Y = lambda *a: X("Y", "retry", 0, *a)
    Y(W, "Open Notepad", ["click Start", "type notepd"], "type notepd",
      "Start menu | Search: notepd | No results found", "page changed")
    Y(W, "Click the Save button", ["click at (300,700)"], "click at (300,700)",
      'Editor | Button "Save" at (300,660) | (the click landed on empty space below the button)', "no change since last step")
    Y(L, "List files in long format", ["open terminal", "type lss -l"], "press Enter",
      "$ lss -l\nbash: lss: command not found\n$ _", "terminal output appeared")
    Y(W, "Open the Settings app", ["press Win+I"], "press Win+I",
      "Desktop | (no window opened)", "no change since last step")
    Y(W, "Select the file report.docx", ["open Explorer", "click report.docx"], "click report.docx",
      "Explorer | report.docx | budget.xlsx (selected) | notes.txt", "selection changed")
    Y(W, "Fill in the email field", ["click Email field", "type alice@example.com"], "type alice@example.com",
      "Contact form | Name [alice@example.com] (focused) | Email [empty]", "text entered in the wrong field")
    Y(L, "Go to the Documents folder", ["open terminal", "type cd Documnts"], "press Enter",
      "$ cd Documnts\nbash: cd: Documnts: No such file or directory\n$ _", "terminal output appeared")

    P = lambda *a: X("P", "replan", 0, *a)
    P(W, "Install 7-Zip", ["open Edge", "open 7-zip.org"], "open 7-zip.org",
      "Edge | This site can't be reached | 7-zip.org took too long to respond. | ERR_CONNECTION_TIMED_OUT", "page changed")
    P(W, "Open the budget spreadsheet", ["open Excel", "open budget.xlsx"], "open budget.xlsx",
      "Excel | We couldn't find budget.xlsx. It may have been moved, renamed or deleted.", "modal dialog appeared")
    P(W, "Check email in Outlook", ["click taskbar icon"], "click taskbar icon",
      "Chrome | YouTube - cat video playing | (Outlook is not open)", "page changed")
    P(L, "Install foo", ["open terminal", "type sudo apt install foo"], "press Enter",
      "E: Unable to locate package foo\n$ _", "terminal output appeared")
    P(W, "Pay the invoice online", ["open billing.example.com/pay"], "open billing.example.com/pay",
      "404 - Page not found | The page you are looking for does not exist.", "page changed")
    P(W, "Print the report", ["open report.docx", "press Ctrl+P"], "press Ctrl+P",
      'Print | No printers are installed. | Button "Add a printer"', "page changed")
    P(L, "Run the build", ["open terminal", "type make"], "press Enter",
      "make: *** No rule to make target 'all'.  Stop.\n$ _", "terminal output appeared")

    # derive next / last_ok for the original cases, then hand-fix the ones that are not the default
    override = {  # id -> (next, last_ok)
        "N01": ("retry", 0), "N16": ("replan", 0), "N17": ("done", 1), "N06": ("done", 1), "N05": ("done", 1),
        "N22": ("done", 1), "N26": ("done", 1), "N14": ("done", 1), "N15": ("done", 1),
    }
    for r in rows:
        if "next" in r:
            continue
        nxt = "ask_user" if r["risky"] else "replan" if r["stuck"] else "continue"
        r["next"], r["last_ok"] = override.get(r["id"], (nxt, 0 if nxt == "replan" else 1))
