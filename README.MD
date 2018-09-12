# FTP Client

This is a FTP Client to download and fetch the list of files and directories, with customizable checking functions.

## Requirements
This program only works for Python 3.6+, due to type checking and changing exception names.

## Usage
Upon using a FTP client, closing the client after used is RECOMMENDED, as the server may close your connection after timed-out.

The returned files and directories from `get_files()` and `get_directories()` are in `FTPFile` format. `FTPFile` is a `namedtuple` object with 3 attributes: `name`, `size` and `modified_date`.

### 1. Connect to your FTP server
```
from ftp_client import FTPClient

if __name__ == "__main__":
    hostname = "YOUR FTP HOSTNAME"
    username = "foo"
    password = "bar"

    client = FTPClient()
    client.connect(hostname)
    client.login(username, password)

    # Do sth

    # Closing the connection after used is recommended
    client.close()
```

### 2. Get the files and sub-directories in the `root` directory
```
files = client.get_files()
directories = client.get_directories()

print(files)
print(directories)
```

### 3. Download all files in `root` and all sub-directories
```
import os.path
...

def download_all_files(path: str=''):
    # Get the directories in the current working directory (root)
    directories_in_root = client.get_directories()

    for directory in iter(directories_of_main):
        directory_path = os.path.join(path, directory.name)

        # Get the sub_directories
        sub_directories = client.get_directories(directory_path)

        # If there exists sub-directories in the cwd
        if len(sub_directories) > 0:
            # Traverse to all sub-directories
            for sub_directory in sub_directories:
                download_all_files(directory_path)

        client.download_files_in_directory(directory_path)
```

### 4. Change download directory
```
another_download_directory = "hello_from_the_other_side"
client = FTPClient(download_dir=another_download_directory)
```

### 5. Custom file checking function
The FTP Client accepts functions that takes in a `FTPFile` and returns True/False to only add the satisfied files/directories.

```
def is_correct_tar_file(file_info: FTPFile) -> bool:
    """Check if the file is in the right compressed format."""

    if file_info.name.endswith('_xml.tar.gz'):
        return True
    return False

client = FTPClient(file_checking_function=is_correct_tar_file)
...

# Only return the files that `is_correct_tar_file` returns True
files = client.get_files()
```

### 6. Advanced directory checking
As `ftplib` doesn't have an in-built directory checking function, so by default, the FTP Client assumes that objects having no extensions are directories.

A walkaround is to send a get-size request to the server. If the response is an error, the object is a directory. However, a latency for the request is expected.

To enable the sending get-size request, set `request_check_is_dir` in `FTPClient` to be `True`:
```
client = FTPClient(request_check_is_dir=True)
```

Moreover, you can self-modify the checking directory function in this `FTPClient` by editing function `__is_directory(filename: str)` in `ftp_client.py`.
