# Notes on creation of parser output fixtures

Each directory represents the output of a specific `pw.x` run that is supposed to tests a specific path of the `PwParser`.
Each test will mock a `CalcJobNode` and attach a `FolderData` as `retrieved` output node, the contents of which are based on the files in the fixture directory.
The parser will parse those files and produce certain output nodes, which are then checked for consistency.

Many of the tests will only test a very specific case of a `pw.x` outcome, but the parser will require at least the standard output and XML file, nonetheless.
Simply including the actual output files for all these corner cases, will quickly bloat the repository.
Instead, the main parsing functionality should be tested in a single "successful" test, where also the content of the generated output nodes is checked.
For the various tests that test a particular failing mode, often the exact content of the output nodes is not crucial to test for.
Rather, one wants to verify that the desired exit code is returned.
In these cases, the output files are manually crafted to contain as little information as necessary while still testing this particular failure mode.
Note then that the output files are by definition not representative of actual runs and are based on a very simple example case and then modified.

