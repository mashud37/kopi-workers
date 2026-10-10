# kopi-workers 0.1.0 (unreleased)

The first release: kopi-editor, kopi-presenter and kopi-console in one package.

* The tools, until now separate repositories, are merged into this one repository under
  `workers/`, each with its full history.
* `pip install kopi-workers` installs every tool with everything it needs. One command per tool:
  `kopi-editor`, `kopi-presenter` and `kopi-console`. Each opens that tool's own menu, and every
  menu action is also a subcommand.
* `kopi-console` opens one local web page over the editor and the presenter: drop a file, run a
  command, watch its log, open what it wrote. Its Settings card chooses each tool's model, and its
  Keys page holds the API keys.
* Every tool keeps its files in one project folder, `kopi-workers` in the home folder.
* kopi-editor downloads spaCy's English model the first time it needs it.
* kopi-editor writes a side-by-side table of each paragraph before and after.
* Developed and tested on Windows; macOS and Linux are untested.
