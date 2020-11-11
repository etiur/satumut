from pmx import Model
from pmx.rotamer import load_bbdep
import argparse
import os
from helper import map_atom_string
from pmx.library import _aacids_dic
from pmx.rotamer import get_rotamers, select_best_rotamer
from os.path import basename
from multiprocessing import Process


# Argument parsers
def parse_args():
    parser = argparse.ArgumentParser(description="Performs saturated mutagenesis given a PDB file")
    # main required arguments
    parser.add_argument("--input", required=True, help="Include PDB file's path")
    parser.add_argument("--position", required=True, nargs="+",
                        help="Include one or more chain IDs and positions --> ID:position")
    parser.add_argument("--multiple", required=False, action="store_true")

    # arguments = vars(parser.parse_args())
    args = parser.parse_args()
    return args.input, args.position, args.multiple


class SaturatedMutagenesis:

    def __init__(self, model, position):
        """
        model (str) path to the PDB file
        position (str) chain ID:position of the residue, for example A:132
        """
        self.model = Model(model)
        self.input = model
        self.coords = position
        self.rotamers = load_bbdep()
        self.residues = ['ALA', 'CYS', 'GLU', 'ASP', 'GLY', 'PHE', 'ILE', 'HIS', 'LYS', 'MET', 'LEU', 'ASN', 'GLN',
                         'PRO', 'SER', 'ARG', 'THR', 'TRP', 'VAL', 'TYR']
        self.final_pdbs = []
        self.chain = None
        self.chain_id = None
        self.position = None

    def mutate(self, residue, new_aa, bbdep, hydrogens):
        if len(new_aa) == 1:
            new_aa = _aacids_dic[new_aa]
        phi = residue.get_phi()
        psi = residue.get_psi()
        rotamers = get_rotamers(bbdep, new_aa, phi, psi, residue=residue, full=True, hydrogens=hydrogens)
        new_r = select_best_rotamer(self.model, rotamers)
        self.model.replace_residue(residue, new_r)

    def check_coords(self, mode=0):
        """
        map the user coordinates with pmx coordinates
        """
        if not os.path.exists("pdb_files"):
            os.mkdir("pdb_files")
        if not mode:
            self.model.write("pdb_files/original.pdb")
            self.final_pdbs.append("pdb_files/original.pdb")

        after = map_atom_string(self.coords, self.input, "pdb_files/original.pdb")
        self.chain_id = after.split(":")[0]
        self.position = int(after.split(":")[1]) - 1

        for chain_ in self.model.chains:
            if chain_.id == self.chain_id:
                self.chain = chain_

    def generate_pdb(self, hydrogens=True, mode=0, name=None):
        """
        Generate all the other 19 mutations
        """
        aa_name = self.chain.residues[self.position].resname
        invert_aa = {v: k for k, v in _aacids_dic.items()}
        aa_ = invert_aa[aa_name]
        for aa in self.residues:
            if aa != aa_name:
                self.mutate(self.chain.residues[self.position], aa, self.rotamers, hydrogens=hydrogens)
                if not mode:
                    output = "{}{}{}.pdb".format(aa_, self.position + 1, invert_aa[aa])
                else:
                    output = "{}_{}{}{}.pdb".format(name, aa_, self.position + 1, invert_aa[aa])

                self.model.write("pdb_files/{}".format(output))
                self.final_pdbs.append("pdb_files/{}".format(output))

        return self.final_pdbs

    def insert_atomtype(self, prep_pdb):
        """
        modifies the pmx PDB files to include the atom type
        """
        # read in user input
        with open(self.input, "r") as initial:
            initial_lines = initial.readlines()

        # read in preprocessed input
        with open(prep_pdb, "r") as prep:
            prep_lines = prep.readlines()

        for ind, line in enumerate(prep_lines):
            if (line.startswith("HETATM") or line.startswith("ATOM")) and (
                    line[21].strip() != self.chain_id.strip() or line[
                                                                 22:26].strip() != str(self.position + 1)):
                coords = line[30:54].split()
                for linex in initial_lines:
                    if linex[30:54].split() == coords:
                        prep_lines[ind] = line.strip("\n") + linex[66:81]
                        break

            elif (line.startswith("HETATM") or line.startswith("ATOM")) and line[
                21].strip() == self.chain_id.strip() and line[
                                                         22:26].strip() == str(self.position + 1):

                atom_name = line[12:16].strip()
                if atom_name[0].isalpha():
                    atom_type = "           {}  \n".format(atom_name[0])
                else:
                    atom_type = "           {}  \n".format(atom_name[1])

                prep_lines[ind] = line.strip("\n") + atom_type

        # rewrittes the files now with the atom type
        with open(prep_pdb, "w") as prep:
            prep.writelines(prep_lines)

    def accelerated_insert(self):
        pros = []
        for prep_pdb in self.final_pdbs:
            p = Process(target=self.insert_atomtype, args=(prep_pdb,))
            p.start()
            pros.append(p)
        for p in pros:
            p.join()


def generate_multiple_mutations(input_, position, hydrogens=True):
    """
        To generate a combination of mutations
        input (str): Input pdb to be used to generate the mutations
        position (list): [chain ID:position] of the residue, for example [A:139,..]
    """
    count = 0
    pdbs = []
    # Perform single saturated mutations
    for mutation in position:
        run = SaturatedMutagenesis(input_, mutation)
        if not count:
            run.check_coords()
        else:
            run.check_coords(mode=1)
        final_pdbs = run.generate_pdb(hydrogens=hydrogens)
        pdbs.extend(final_pdbs)
        run.accelerated_insert()
        # Mutate in a second position for each of the single mutations
        if not count and len(position) == 2:
            for files in final_pdbs:
                name = basename(files)
                if name != "original.pdb":
                    name = name.replace(".pdb", "")
                    run_ = SaturatedMutagenesis(files, position[1])
                    run_.check_coords(mode=1)
                    final_pdbs_2 = run_.generate_pdb(hydrogens=hydrogens, mode=1, name=name)
                    pdbs.extend(final_pdbs_2)
                    run_.accelerated_insert()

            count += 1

    return pdbs


def generate_mutations(input_, position, hydrogens=True):
    """
        To generate single point mutations
        input (str): Input pdb to be used to generate the mutations
        position (list): [chain ID:position] of the residue, for example [A:139,..]
    """
    count = 0
    pdbs = []
    for mutation in position:
        run = SaturatedMutagenesis(input_, mutation)
        if not count:
            run.check_coords()
        else:
            run.check_coords(mode=1)
        final_pdbs = run.generate_pdb(hydrogens=hydrogens)
        pdbs.extend(final_pdbs)
        run.accelerated_insert()
        count += 1

    return pdbs


def main():
    input_, position, multiple = parse_args()
    if multiple:
        output = generate_multiple_mutations(input_, position)
    else:
        output = generate_mutations(input_, position)

    return output


if __name__ == "__main__":
    # Run this if this file is executed from command line but not if is imported as API
    all_pdbs = main()
