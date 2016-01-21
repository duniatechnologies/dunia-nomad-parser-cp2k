import re
import logging
from cp2kparser.utils.baseclasses import Parser
from cp2kparser.parsing.implementations import *
logger = logging.getLogger(__name__)


#===============================================================================
class CP2KParser(Parser):
    """Builds the correct parser by looking at the given files and the given
    input.

    This class handles the initial setup before any parsing can happen. It
    determines which version of CP2K was used to generate the output and then
    sets up a correct implementation.

    After the implementation has been setup, you can parse the files with
    parse().
    """

    def __init__(self, contents=None, metainfo_to_keep=None, backend=None):
        Parser.__init__(self, contents, metainfo_to_keep, backend)

    def setup(self):
        """Setups the version by looking at the output file and the version
        specified in it.
        """
        # Search for the output file
        count = 0
        for filepath in self.parser_context.files:
            if filepath.endswith(".out"):
                count += 1
                outputpath = filepath
        if count > 1:
            logger("Could not determine the correct outputfile because multiple files with extension '.out' were found.")
            return
        elif count == 0:
            logger.error("No output file could be found. The outputfile should have a '.out' extension.")
            return

        # Search for the version specification
        outputfile = open(outputpath, 'r')
        regex = re.compile(r" CP2K\| version string:\s+CP2K version ([\d\.]+)")
        for line in outputfile:
            result = regex.match(line)
            if result:
                self.parser_context.version_id = result.group(1).replace('.', '')
                break

        # Search and initialize a version specific implementation
        class_name = "CP2KImplementation{}".format(self.parser_context.version_id)
        class_object = globals().get(class_name)
        if class_object:
            logger.debug("Using version specific implementation '{}'.".format(class_name))
            self.implementation = class_object(self.parser_context)
        else:
            logger.debug("No version specific implementation found. Using the default implementation: {}".format(class_name))
            self.parser_context.version_id = "262"
            self.implementation = globals()["CP2KImplementation262"](self.parser_context)

    def search_parseable_files(self, files):
        """Searches the given path for files that are of interest to this
        parser. Returns them as a list of path strings.
        """
        return files

    def get_metainfo_filename(self):
        """This function should return the name of the metainfo file that is
        specific for this parser. This name is used by the Analyzer class in
        the nomadtoolkit.
        """
        return "cp2k.nomadmetainfo.json"