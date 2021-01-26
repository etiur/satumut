"""
This module provides test of the simulations.py's functions and classes
"""
from ..simulation import SimulationRunner
from subprocess import Popen


class TestSimulationRunner:
    """
    It is a class that tests the SimulationRunner class
    """
    def test_submit(self):
        """
        Test the submit function in SimulationRunner
        """
        simulation = SimulationRunner("data/test/PK2_F454T.pdb")
        simulation.submit("data/test/test.yaml")
        assert isinstance(simulation.commands, list), "incorrect command format"
        assert isinstance(simulation.proc[0], Popen), "Submit isn't returning a subprocess.Popen object"