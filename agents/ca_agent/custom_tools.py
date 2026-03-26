import glob
import subprocess


def list_code_files(directory_path: str = ".") -> list[str]:
    """Lists all Python, markdown, and .env files in the given directory to help locate code and config."""
    files = []
    files.extend(glob.glob(f"{directory_path}/**/*.py", recursive=True))
    files.extend(glob.glob(f"{directory_path}/**/*.md", recursive=True))
    files.extend(glob.glob(f"{directory_path}/**/.env*", recursive=True))
    return files


def read_code_file(file_path: str) -> str:
    """Reads the contents of a specific code file so you can inspect it for bugs."""
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {file_path}: {e}"


def run_gemini_cli(command_args: str) -> str:
    """Executes the gemini CLI tool with the provided arguments and returns the output.

    Args:
        command_args: The arguments to pass to the `gemini` CLI (e.g., 'models list', 'generate --prompt "..."'). Do NOT include the word `gemini`.
    """
    try:
        full_command = f"gemini {command_args}"
        result = subprocess.run(
            full_command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout or "Command executed successfully with no output."
    except subprocess.CalledProcessError as e:
        return f"Error executing gemini CLI:\\nSTDOUT: {e.stdout}\\nSTDERR: {e.stderr}"
    except Exception as e:
        return f"Unexpected error executing gemini CLI: {e}"
