import time
import zipfile
import logging

LOGGER = logging.getLogger(__name__)

class ZipArchive(object):
    """
    Read, write, access Zip archives using zipfile.
    """
    def __init__(self, path, mode='w'):
        """
        Initialize a ZipArchive.
        
        Arguments:
        
        path -- Path to the archive file
        mode -- Archive mode.  Default: w (write) (see zipfile)
        """
        self.path = path
        self.mode = mode
        self.archive = zipfile.ZipFile(path, 
                                       mode, 
                                       zipfile.ZIP_DEFLATED, 
                                       True)

    def add_file(self, path, name):
        """
        Add a file to the archive.
        
        Arguments:
        
        path -- Path to file for which to add to archive.
        name -- Name of file to save in the archive
        """
        self.archive.write(path, name, zipfile.ZIP_DEFLATED)

    def add_string(self, str, name):
        """
        Add a string to the archive (fake file).
        
        Arguments:
        
        string  -- String to add to the archive.
        name    -- Name of the file to save string as.
        """
        self.archive.writestr(name, str)

    def list(self):
        """
        List contents of the archive.  Returns a list of member names.
        """
        result = []
        for member in self.archive.namelist():
            result.append(member)
        return result

    def extract(self, name, dest):
        """
        Extract a member from an archive to 'dest' path.
        
        Arguments:
        
        name -- Name of the member in the archive to extract.
        dest -- Path to extract member to.
        """
        self.archive.extract(name, dest)

    def close(self):
        """
        Close archive.
        """
        self.archive.close()

if __name__ == '__main__':
    now = time.time()
    xv = ZipArchive('foo.zip', 'w')
    xv.add_string("[mysqldump]\nignore-table=mysql.user\n", "my.cnf")
    xv.add_string("blah", "test/test.MYD")
    xv.add_file("user.frm", "mysql/user.frm")
    xv.add_file("user.MYD", "mysql/user.MYD")
    xv.add_file("user.MYI", "mysql/user.MYI")
    xv.close()
    print (time.time() - now), "seconds"
