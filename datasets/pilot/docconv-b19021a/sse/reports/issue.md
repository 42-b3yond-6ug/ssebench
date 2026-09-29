### Root Cause

docconv's PDF image detection feature constructs a shell command that embeds a caller-supplied file path using `fmt.Sprintf`. The resulting command string is then executed via `exec.Command("bash", "-c", <command>)`, which invokes the bash shell to interpret the entire command string.

Because the file path is interpolated directly into the command string without any sanitization or escaping, shell metacharacters present in the path are interpreted by bash as shell syntax rather than as literal filename characters. For example:

- `$()` or backticks cause bash to execute the enclosed expression as a subshell command before running the outer command.
- `;` causes bash to treat what follows as a separate, independent command.
- `|` pipes the output of the first command into a second attacker-controlled command.

An attacker who controls the file path argument — for instance through a user-supplied filename — can craft a path containing any of these metacharacters to inject and execute arbitrary shell commands.

### Impact

Any application that passes attacker-controlled input to docconv's PDF image detection is vulnerable to OS command injection. A successful exploit allows arbitrary command execution with the privileges of the running process, affecting confidentiality, integrity, and availability of the system.

**Users are impacted when all of the following apply:**

- The application uses docconv's PDF image detection functionality.
- The file path passed to the function is derived from untrusted input (e.g., user-uploaded filenames, URL parameters, or any other external source).
- The server has `pdffonts` (from poppler-utils) installed, which is required for the vulnerable code path to execute.
