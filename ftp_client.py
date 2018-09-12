from ftplib import FTP
import os
import sys
import ntpath
from collections import namedtuple
import logging
import json
from typing import Callable, List, Union, Dict

# Init the logger for FTP __client
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Init an object to store the information of the files in FTP server
FTPFile = namedtuple('FTPFile', ('name', 'size', 'modified_date'))
FTPFile.__new__.__defaults__ = ('', 0, '')


class FTPClient:
    """
    :params:
        :hostname: (str) (Default: None)
            The hostname (URL) of the FTP server.
            If not specified, use method `self.connect(hostname)` later.

        :download_dir: (str) (Default: downloaded_ftp)
            The directory to store the downloaded files.

        :file_checking_function: (Callable) (Default: None)
            A boolean function that takes in a <FTPFile>.
            Only the <FTPFile> objects being returned True will be added.
            Return all files if file_checking_function=None.

        :history_filename: (str) (Default: None)
            The filename of the text file containing the details of the downloaded files.
            If None, no details are stored.

        :request_check_is_dir: (bool) (Default: False)
            If True, send a request to the FTP server to check if it is a directory.
            If False, assume that an object is a directory if it has no extension.
    """

    def __init__(
            self,
            hostname: str=None,
            *,
            download_dir: str="downloaded_ftp",
            file_checking_function: Callable=None,
            history_filename: str=None,
            request_check_is_dir: bool=False
            ):
        self.download_dir = download_dir
        self.request_check_is_dir = request_check_is_dir
        self.__client = FTP(hostname)
        self.__files = []
        self.__directories = []
        self.__file_checking_function = file_checking_function
        self.__history_filename = history_filename
        self.__downloaded_files = []

        self.__create_the_output_directory(download_dir)


    ## Create the download directory whenever its changed
    @property
    def download_dir(self):
        return self.__download_dir

    @download_dir.setter
    def download_dir(self, new_directory):
        self.__create_the_output_directory(new_directory)
        self.__download_dir = new_directory


    ## PUBLIC ##

    def connect(self, hostname: str):
        """Connect to the hostname using a FTP client."""
        try:
            self.__client.connect(hostname)
        except Exception:
            logger.error(" Failed to connect to {}. Please check your internet connection.".format(hostname))
            sys.exit()

    def close(self):
        """Close the connection with the FTP server."""
        try:
            # Politely close the connection
            self.__client.quit()
        except Exception:
            # The server may raise an exception if the server responds with an error to the QUIT command
            self.__client.close()

    def login(self, username: str='', password: str=''):
        """Login to the connected hostname using the username and password."""
        try:
            self.__client.login(username, password)
        except Exception:
            logger.error(" Failed to login to {}. Please check your credentials or/and internet connection.".format(self.hostname))
            self.close()
            sys.exit()

    def get_files(self, path: str='') -> List[FTPFile]:
        """Return the list of files in the indicated directory. Default: current directory."""

        # Current working directory (cwd)
        if path=='':
            # The list of files in cwd is always updated to avoid duplicated requests
            if not self.__files:
                self.__update_files_and_directories_in_cwd()
            files = self.__files
        else:
            file_infos = self.__get_file_infos(path)
            files, _ = self.__split_files_and_directories(file_infos)

        return files

    def get_directories(self, path: str='') -> List[FTPFile]:
        """Return the list of directories in the indicated directory. Default: current directory."""

        # Current working directory (cwd)
        if path=='':
            # The list of directories in cwd is always updated to avoid duplicated requests
            if not self.__directories:
                self.__update_files_and_directories_in_cwd()
            directories = self.__directories
        else:
            file_infos = self.__get_file_infos(path)
            _, directories = self.__split_files_and_directories(file_infos)

        return directories

    def cwd(self, path: str):
        """Change current working directory."""
        self.__client.cwd(path)

        # Remove all elements in the saved files and directories for cwd
        self.__files.clear()
        self.__directories.clear()

    def download_files_in_directory(self, path: str=''):
        """Download the datasets in the indicated directory. Default: current directory."""
        if len(self.__downloaded_files)  < 1:
            self.__get_previously_downloaded_files()

        files = self.get_files(path)
        file_checking_function = self.__file_checking_function

        # Remove unnecessary files
        if file_checking_function is not None:
            files = filter(file_checking_function, files)

        files = filter(self.__havent_been_downloaded, files)

        for download_file in iter(files):
            self.__download(download_file)


    ## PRIVATE ##

    def __download(self, file_info: FTPFile):
        """Download the filename in the cwd into local `self.download_dir`."""
        try:
            path_to_file = file_info.name
            filename = self.__get_filename_from_path(path_to_file)
            output_filename = self.__join_os_path(self.download_dir, filename)

            logger.info(' Downloading {}'.format(path_to_file))
            with open(output_filename, 'wb') as output_file:
                self.__client.retrbinary('RETR {}'.format(path_to_file), output_file.write)
        except Exception:
            logger.error('Failed to download {}'.format(path_to_file))
            sys.exit()

        # Update the download history after finishing downloading
        if self.__history_filename is not None:
            file_info_as_dict = dict(
                # _asdict() returns an <OrderedDict>
                file_info._asdict()
            )
            self.__append_json_to_list_in_file(file_info_as_dict, self.__history_filename)

    def __update_files_and_directories_in_cwd(self):
        """Retrive the files and directories in CWD and store them in `self` to avoid duplicated requests in CWD. """
        file_infos = self.__get_file_infos('')
        files, directories = self.__split_files_and_directories(file_infos)

        self.__files = files
        self.__directories = directories

    def __get_file_infos(self, path: str='') -> List[FTPFile]:
        """Retrive the files and directories from the FTP server."""

        # Retrive the files' information in the format:
        # "drwxr-xr-x    2 ftp      ftp          4096 Mar 01  2018 092018"
        raw_dir_strings = []
        self.__client.retrlines('LIST {}'.format(path), raw_dir_strings.append)

        # Convert the raw strings into <FTPFile> object
        file_infos = self.__split_file_infos_from_strings(raw_dir_strings)

        # Clear the raw list, to avoid high memory usage
        raw_dir_strings.clear()

        # Add current path to the file_info.name
        file_infos_added_path = list(map(
            lambda file_info: self.__update_file_info_name_with_path(file_info, path), file_infos
        ))

        return file_infos_added_path

    def __split_file_infos_from_strings(self, strings: str) -> List[FTPFile]:
        """Collect the required values from the raw strings into <FTPFile> objects."""

        file_infos = []
        for dir_string in iter(strings):
            # Only the modified date and file_name are interested
            _, _, _, _, file_size, *modified_date_as_list, file_name = dir_string.split()
            modified_date = ' '.join(modified_date_as_list)

            file_infos.append(
                FTPFile(file_name, int(file_size), modified_date)
            )
        return file_infos

    def __split_files_and_directories(self, files_and_directories: List[FTPFile]) -> Union[List[FTPFile], List[FTPFile]]:
        """Split the input list into 2 lists of files and directories."""
        files = []
        directories = []

        for file_info in iter(files_and_directories):
            if self.__is_directory(file_info.name):
                directories.append(file_info)
            else:
                files.append(file_info)
        return files, directories

    def __update_file_info_name_with_path(self, file_info: FTPFile, path: str) -> FTPFile:
        """Join the input path with the FTPFile's name."""
        # As `named_tuple` objects are immutable, a new object must be created
        new_file_info = FTPFile(
            self.__join_os_path(path, file_info.name),
            file_info.size,
            file_info.modified_date
        )
        return new_file_info

    def __get_filename_from_path(self, path: str) -> str:
        """Return the filename from path."""
        head, tail = ntpath.split(path)
        return tail or ntpath.basename(head)

    def __create_the_output_directory(self, output_directory: str):
        """Create the output directory if it doesnt not exist."""
        _current_directory = os.getcwd()
        path = self.__join_os_path(_current_directory, output_directory)

        if self.__file_doesnt_exist(path):
            os.makedirs(path)

    def __join_os_path(self, *args):
        return os.path.join(*args)

    def __append_json_to_list_in_file(self, new_json_data, filename):
        """Write JSON data to file."""

        # Read the current list of downloaded files
        able_to_read_file = False
        try:
            with open(filename, encoding='utf-8', errors='replace') as json_read_file:
                downloaded_files = json.load(json_read_file)
            able_to_read_file = True

        except FileNotFoundError:
            logger.info(" Creating a new downloaded history file {}.".format(filename))
        except Exception:
            logger.error(" Unable to read history downloaded file {}".format(filename))
            logger.warning(" Ignored and create a new one.")

        if able_to_read_file and len(downloaded_files) > 0:
            downloaded_files.append(new_json_data)
        else:
            downloaded_files = [new_json_data]

        with open(filename, 'w', encoding='utf-8') as output_file:
            json.dump(downloaded_files, output_file, indent=2, skipkeys=False, ensure_ascii=False)

        # Update the local download_files as well
        self.__downloaded_files.append(new_json_data)

    def __get_previously_downloaded_files(self) -> List[Dict]:
        """Return a <set> containing the downloaded file info from the input JSON file."""

        filename = self.__history_filename
        try:
            with open(filename, encoding='utf-8', errors='replace') as json_read_file:
                downloaded_files = json.load(json_read_file)

            if self.__is_json_of_downloaded_file_info_in_correct_format(downloaded_files):
                    self.__downloaded_files = downloaded_files
            return downloaded_files

        except FileNotFoundError:
            pass
        except json.decoder.JSONDecodeError:
            logger.error(" Unable to read the history downloaded file {}.".format(filename))
            logger.warning(" Ignored and proceed to download the files.")

        return []

    ## Boolean check

    def __file_doesnt_exist(self, path: str):
        """Return True if the file exists; otherwise, return False."""
        return not os.path.exists(path)

    def __havent_been_downloaded(self, file_info: FTPFile):
        """Check if the input <FTPFile> is in the list of downloaded files."""

        # Convert the FTPFile input into a <dict> to compare with downloaded ones
        file_info_as_dict = dict(
            # _asdict() returns an <OrderedDict>
            file_info._asdict()
        )
        return all(
            file_info_as_dict != downloaded_file_info
            for downloaded_file_info in self.__downloaded_files
        )

    def __is_json_of_downloaded_file_info_in_correct_format(self, json_data: List[dict]):
        """Check if the file info JSON is in the correct format."""

        """
        The format of the JSON should be like :
        [
            {
                'name': 'ipg150519.tar.gz',         # (str)
                'size': 11134012,                   # Bytes (int)
                'modified_date': 'Mar 01  2018'     # (str)
            },
            ...
        ]
        """

        for file_info in iter(json_data):
            if (not isinstance( file_info.get('name', ''), str)  or
                not isinstance( file_info.get('size', 0), int) or
                not isinstance( file_info.get('modified_date', ''), str)
                ):
                return False

        return True

    ## Custom checking function as ftplib doesnt have an in-built one
    def __is_directory(self, filename: str):
        """Check if the filename is a directory"""

        ## Filesize request can be sent to check if it is a directory.
        ## However, a long latency is expected.
        ## For now, only check for extension of the filename
        extension = os.path.splitext(filename)[-1]
        have_filesize = True

        # By default, using request to check filesize is set to False
        if self.request_check_is_dir:
            try:
                # A latency of the size request is expected
                # Checking size can be removed, but working with files
                # and directories at risk
                size_of_file = self.__client.size(filename)
            except Exception:
                # If the file is a directory, a Exception is raised
                have_filesize = False

        if extension == '' and have_filesize:
            return True

        return False
