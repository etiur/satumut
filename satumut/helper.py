import logging


def map_atom_string(atom_string, initial_pdb, prep_pdb):
    """
    Maps the chain ID and residue number of the original PDb file to the PDB file after pmx

    Parameters
    ___________
    atom_string: str
        The positions to map
    initial_pdb: str
        The original PDB
    prep_pdb: str
        The changed PDB

    Return
    _______
    after: str
        The new atom string or position
    """
    # read in user input
    with open(initial_pdb, "r") as initial:
        initial_lines = initial.readlines()

    # read in preprocessed input
    with open(prep_pdb, "r") as prep:
        prep_lines = prep.readlines()

    # split the atom string or retrieve from the number
    if len(atom_string.split(":")) == 3:
        chain, resnum, atom_name = atom_string.split(":")
        # extract coordinates from user input
        for i in initial_lines:
            if (i.startswith("HETATM") or i.startswith("ATOM")) and i[21].strip() == chain.strip() and i[
                    22:26].strip() == resnum.strip() and i[12:16].strip() == atom_name.strip():

                coords = i[30:54].split()

                # extract coordinates from preprocessed file
                for p in prep_lines:
                    if p[30:54].split() == coords:
                        new_atom_name = p[12:16].strip()
                        new_resnum = p[22:26].strip()
                        new_chain = p[21].strip()
                        after = "{}:{}:{}".format(new_chain, new_resnum, new_atom_name)
                        break
                break

    else:
        chain, resnum = atom_string.split(":")
        for i in initial_lines:
            if (i.startswith("HETATM") or i.startswith("ATOM")) and i[21].strip() == chain.strip() and i[
                                                                    22:26].strip() == resnum.strip():
                coords = i[30:54].split()

                # extract coordinates from preprocessed file
                for p in prep_lines:
                    if p[30:54].split() == coords:
                        new_resnum = p[22:26].strip()
                        new_chain = p[21].strip()
                        after = "{}:{}".format(new_chain, new_resnum)
                        break
                break

    return after


def isiterable(p_object):
    """
    Test if the parameter is an iterable (not a string or a dict) or a file

    Parameters
    ___________
    p_object: object
        Any object

    Returns
    _______
    True: bool
        Returns true if the conditions are met
    """
    if type(p_object) == str or type(p_object) == dict:
        return False
    try:
        iter(p_object)
    except TypeError:
        return False
    return True

class Log:
    """
    A class to keep log of the output from different modules
    """

    def __init__(self, name):
        """
        Initialize the Log class
        Parameters
        __________
        name: str
            The name of the log file
        """
        self._logger = logging.getLogger(__name__)
        self._logger.handlers = []
        self._logger.setLevel(logging.DEBUG)
        self.fh = logging.FileHandler("{}.log".format(name))
        self.fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.fh.setFormatter(formatter)
        self._logger.addHandler(self.fh)

    def debug(self, messages, exc_info=False):
        """
        It pulls a debug message.
        Parameters
        ----------
        messages : str
            The messages to log
        exc_info : bool, optional
            Set to true to include the exception error message
        """
        self._logger.debug(messages, exc_info=exc_info)

    def info(self, messages, exc_info=False):
        """
        It pulls an info message.
        Parameters
        ----------
        messages : str
            The messages to log
        exc_info : bool, optional
            Set to true to include the exception error message
        """
        self._logger.info(messages, exc_info=exc_info)

    def warning(self, messages, exc_info=False):
        """
        It pulls a warning message.
        Parameters
        ----------
        messages : str
            The messages to log
        exc_info : bool, optional
            Set to true to include the exception error message
        """
        self._logger.warning(messages, exc_info=exc_info)

    def error(self, messages, exc_info=False):
        """
        It pulls a error message.
        Parameters
        ----------
        messages : str
            The messages to log
        exc_info : bool, optional
            Set to true to include the exception error message
        """
        self._logger.error(messages, exc_info=exc_info)

    def critical(self, messages, exc_info=False):
        """
        It pulls a critical message.
        Parameters
        ----------
        messages : str
            The messages to log
        exc_info : bool, optional
            Set to true to include the exception error message
        """
        self._logger.critical(messages, exc_info=exc_info)