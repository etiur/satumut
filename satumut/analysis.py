from glob import glob
import pandas as pd
import seaborn as sns
import argparse
from os.path import basename, dirname, abspath, isdir, isfile, join
import os
import sys
import re
from fpdf import FPDF
import logging
import matplotlib.pyplot as plt
import multiprocessing as mp
from functools import partial
from helper import isiterable
plt.switch_backend('agg')


def parse_args():
    parser = argparse.ArgumentParser(description="Analyse the different PELE simulations and create plots")
    # main required arguments
    parser.add_argument("--inp", required=True,
                        help="Include a file or list with the path to the folders with PELE simulations inside")
    parser.add_argument("--dpi", required=False, default=800, type=int,
                        help="Set the quality of the plots")
    parser.add_argument("--box", required=False, default=30, type=int,
                        help="Set how many data points are used for the boxplot")
    parser.add_argument("--traj", required=False, default=10, type=int,
                        help="Set how many PDBs are extracted from the trajectories")
    parser.add_argument("--out", required=False, default="summary",
                        help="Name of the summary file created at the end of the analysis")
    parser.add_argument("--folder", required=False,
                        help="Path of the plots folder")
    parser.add_argument("--analyse", required=False, choices=("energy", "distance", "all"), default="distance",
                        help="The metric to measure the improvement of the system")
    parser.add_argument("--cpus", required=False, default=24, type=int,
                        help="Include the number of cpus desired")
    parser.add_argument("--thres", required=False, default=-0.1, type=float,
                        help="The threshold for the improvement which will affect what will be included in the summary")
    args = parser.parse_args()

    return [args.inp, args.dpi, args.box, args.traj, args.out, args.folder, args.analyse,
            args.cpus, args.thres]


class SimulationData:
    """
    A class to store data from the simulations
    """
    def __init__(self, folder, points=30, pdb=10):
        """
        Initialize the SimulationData Object

        Parameters
        ___________
        folder: str
            path to the simulation folder
        points: int, optional
            Number of points to consider for the boxplots
        pdb: int, optional
            how many pdbs to extract from the trajectories
        """
        self.folder = folder
        self.dataframe = None
        self.distance = None
        self.dist_diff = None
        self.profile = None
        self.trajectory = None
        self.points = points
        self.pdb = pdb
        self.binding = None
        self.bind_diff = None

    def filtering(self):
        """
        Constructs a dataframe from all the reports in a PELE simulation folder with the best 20% binding energies
        and a Series with the 100 best ligand distances
        """
        pd.options.mode.chained_assignment = None
        reports = []
        for files in glob("{}/output/0/report_*".format(self.folder)):
            rep = basename(files).split("_")[1]
            data = pd.read_csv(files, sep="    ", engine="python")
            data['#Task'].replace({1: rep}, inplace=True)
            data.rename(columns={'#Task': "ID"}, inplace=True)
            reports.append(data)
        self.dataframe = pd.concat(reports)
        self.dataframe.sort_values(by="Binding Energy", inplace=True)
        self.dataframe.reset_index(drop=True, inplace=True)
        self.dataframe = self.dataframe.iloc[:len(self.dataframe) - 99]

        # for the PELE profiles
        self.profile = self.dataframe.drop(["Step", "numberOfAcceptedPeleSteps", 'ID'], axis=1)
        self.trajectory = self.dataframe.sort_values(by="distance0.5")
        self.trajectory.reset_index(drop=True, inplace=True)
        self.trajectory.drop(["Step", 'sasaLig', 'currentEnergy'], axis=1, inplace=True)
        self.trajectory = self.trajectory.iloc[:self.pdb]

        # For the box plots
        data_20 = self.dataframe.iloc[:len(self.dataframe) * 20 / 100]
        data_20.sort_values(by="distance0.5", inplace=True)
        data_20.reset_index(drop=True, inplace=True)
        data_20 = data_20.iloc[:min(self.points, len(data_20))]
        self.distance = data_20["distance0.5"].copy()
        self.binding = data_20["Binding Energy"].copy()
        self.binding.sort_values(inplace=True)
        self.binding.reset_index(drop=True, inplace=True)

        if "original" in self.folder:
            self.distance = self.distance.iloc[0]
            self.binding = self.binding.iloc[0]

    def set_distance(self, original_distance):
        """
        Set the distance difference

        Parameters
        __________
        original_distance: int
            The distrance for the wild type

        """
        self.dist_diff = self.distance - original_distance

    def set_binding(self, original_binding):
        """
        Set the binding energy difference

        Parameters
        __________
        original_binding: int
            The binding energy for the wild type
        """
        self.bind_diff = self.binding - original_binding


def analyse_all(folders=".", box=30, traj=10):
    """
    Analyse all the 19 simulations folders and build SimulationData objects for each of them

    Parameters
    ___________
    folders: str, optional
        path to the different PELE simulation folders to be analyzed
    box: int, optional
        How many points to use for the box plots
    traj: int, optional
        How many snapshots to extract from the trajectories

    Returns
    _______
    data_dict: dict
        Dictionary of SimulationData objects
    """
    data_dict = {}
    if len(folders.split("/")) > 1:
        mutation_dir = dirname(folders)
        original = SimulationData("{}/PELE_original".format(mutation_dir), points=box, pdb=traj)
    else:
        original = SimulationData("PELE_original", points=box, pdb=traj)
    original.filtering()
    data_dict["original"] = original
    for folder in glob("{}/PELE_*".format(folders)):
        name = basename(folder)
        data = SimulationData(folder, points=box, pdb=traj)
        data.filtering()
        data.set_distance(original.distance)
        data.set_binding(original.binding)
        data_dict[name[5:]] = data

    return data_dict


def box_plot(res_dir, data_dict, position_num, dpi=800):
    """
    Creates a box plot of the 19 mutations from the same position

    Parameters
    ___________
    res_dir: str
        name of the results folder
    data_dict: dict
        A dictionary that contains SimulationData objects from the simulation folders
    position_num: str
        Position at the which the mutations occurred
    dpi: int, optional
        The quality of the plots produced
    """
    if not os.path.exists("{}_results/Plots/box".format(res_dir)):
        os.makedirs("{}_results/Plots/box".format(res_dir))
    # create a dataframe with only the distance differences for each simulation
    plot_dict_dist = {}
    plot_dict_bind = {}
    for key, value in data_dict.items():
        if "original" not in key:
            plot_dict_dist[key] = value.dist_diff
            plot_dict_bind[key] = value.bind_diff

    data_dist = pd.DataFrame(plot_dict_dist)
    data_bind = pd.DataFrame(plot_dict_bind)

    # Distance boxplot
    sns.set(font_scale=1.8)
    sns.set_style("ticks")
    sns.set_context("paper")
    ax = sns.catplot(data=data_dist, kind="box", palette="Accent", height=4.5, aspect=2.3)
    ax.set(title="{} distance variation with respect to wild type".format(position_num))
    ax.set_ylabels("Distance variation", fontsize=8)
    ax.set_xlabels("Mutations {}".format(position_num), fontsize=6)
    ax.set_xticklabels(fontsize=6)
    ax.set_yticklabels(fontsize=6)
    ax.savefig("{}_results/Plots/box/{}_distance.png".format(res_dir, position_num), dpi=dpi)

    # Binding energy Box plot
    ex = sns.catplot(data=data_bind, kind="box", palette="Accent", height=4.5, aspect=2.3)
    ex.set(title="{} Binding energy variation with respect to wild type".format(position_num))
    ex.set_ylabels("Binding energy variation", fontsize=8)
    ex.set_xlabels("Mutations {}".format(position_num), fontsize=6)
    ex.set_xticklabels(fontsize=6)
    ex.set_yticklabels(fontsize=6)
    ex.savefig("{}_results/Plots/box/{}_binding.png".format(res_dir, position_num), dpi=dpi)
    plt.close("all")


def pele_profile_single(key, mutation, res_dir, wild, type_, position_num, dpi=800):
    """
    Creates a plot for a single mutation

    Parameters
    ___________
    key: str
        name for the axis title and plot
    mutation: SimulationData
        A SimulationData object
    res_dir: str
        name of the results folder
    wild: SimulationData
        SimulationData object that stores data for the wild type protein
    type_: str
        Type of scatter plot - distance0.5, sasaLig or currentEnergy
    position_num: str
        name for the folder to keep the images from the different mutations
    dpi: int, optional
        Quality of the plots
    """
    # Configuring the plot
    sns.set(font_scale=1.2)
    sns.set_style("ticks")
    sns.set_context("paper")
    original = wild.profile
    original.index = ["Wild type"] * len(original)
    distance = mutation.profile
    distance.index = [key] * len(distance)
    cat = pd.concat([original, distance], axis=0)
    cat.index.name = "Type"
    cat.reset_index(inplace=True)
    # Creating the scatter plots
    if not os.path.exists("{}_results/Plots/scatter_{}_{}".format(res_dir, position_num, type_)):
        os.makedirs("{}_results/Plots/scatter_{}_{}".format(res_dir, position_num, type_))
    ax = sns.relplot(x=type_, y='Binding Energy', hue="Type", style="Type", palette="Set1", data=cat,
                     height=3.5, aspect=1.5, s=80, linewidth=0)

    ax.set(title="{} scatter plot of binding energy vs {} ".format(key, type_))
    ax.savefig("{}_results/Plots/scatter_{}_{}/{}_{}.png".format(res_dir, position_num, type_,
                                                                 key, type_), dpi=dpi)
    plt.close(ax.fig)


def pele_profiles(type_, res_dir, data_dict, position_num, dpi=800):
    """
    Creates a scatter plot for each of the 19 mutations from the same position by comparing it to the wild type

    Parameters
    ___________
    type_: str
        distance0.5, sasaLig or currentEnergy - different possibilities for the scatter plot
    res_dir: str
        Name of the results folder
    data_dict: dict
        A dictionary that contains SimulationData objects from the 19 simulation folders
    position_num: str
        Name for the folders where you want the scatter plot go in
    dpi: int, optional
        Quality of the plots
    """
    for key, value in data_dict.items():
        if "original" not in key:
            pele_profile_single(key, value, res_dir=res_dir, wild=data_dict["original"],
                                type_=type_, position_num=position_num, dpi=dpi)


def all_profiles(res_dir, data_dict, position_num, dpi=800):
    """
    Creates all the possible scatter plots for the same mutated position

    Parameters
    ___________
    res_dir: str
        Name of the results folder for the output
    data_dict: dict
        A dictionary that contains SimulationData objects from the simulation folders
    position_num: str
        name for the folders where you want the scatter plot go in
    dpi: int, optional
        Quality of the plots
    """
    types = ["distance0.5", "sasaLig", "currentEnergy"]
    for type_ in types:
        pele_profiles(type_, res_dir, data_dict, position_num, dpi)


def extract_snapshot_from_pdb(res_dir, simulation_folder, f_id, position_num, mutation, step, dist, bind):
    """
    Extracts PDB files from trajectories

    Parameters
    ___________
    res_dir: str
        Name of the results folder where to store the output
    simulation_folder: str
        Path to the simulation folder
    f_id: str
        trajectory file ID
    position_num: str
        The folder name for the output of this function for the different simulations
    mutation: str
        The folder name for the output of this function for one of the simulations
    step: int
        The step in the trajectory you want to keep
    dist: float
        The distance between ligand and protein (used as name for the result file - not essential)
    bind: float
        The binding energy between ligand and protein (used as name for the result file - not essential)
    """
    if not os.path.exists("{}_results/distances_{}/{}_pdbs".format(res_dir, position_num, mutation)):
        os.makedirs("{}_results/distances_{}/{}_pdbs".format(res_dir, position_num, mutation))

    f_in = glob("{}/output/0/*trajectory*_{}.*".format(simulation_folder, f_id))
    if len(f_in) == 0:
        sys.exit("Trajectory_{} not found. Be aware that PELE trajectories must contain the label 'trajectory' in "
                 "their file name to be detected".format(f_id))
    f_in = f_in[0]
    with open(f_in, 'r') as res_dirfile:
        file_content = res_dirfile.read()
    trajectory_selected = re.search(r'MODEL\s+{}(.*?)ENDMDL'.format(int(step) + 1), file_content, re.DOTALL)

    # Output Snapshot
    traj = []
    path_ = "{}_results/distances_{}/{}_pdbs".format(res_dir, position_num, mutation)
    name = "traj{}_step{}_dist{}_bind{}.pdb".format(f_id, step, round(dist, 2), round(bind, 2))
    with open(os.path.join(path_, name), 'w') as f:
        traj.append("MODEL     {}".format(int(step) + 1))
        try:
            traj.append(trajectory_selected.group(1))
        except AttributeError:
            raise AttributeError("Model not found")
        traj.append("ENDMDL\n")
        f.write("\n".join(traj))


def extract_10_pdb_single(info, res_dir, data_dict):
    """
    Extracts the top 10 distances for one mutation

    Parameters
    ___________
    info: iterable
       An iterable with the variables simulation_folder, position_num and mutation
    res_dir: str
       Name of the results folder
    data_dict: dict
       A dictionary that contains SimulationData objects from the simulation folders
    """
    simulation_folder, position_num, mutation = info
    data = data_dict[mutation]
    for ind in data.trajectory.index:
        ids = data.trajectory["ID"][ind]
        step = data.trajectory["numberOfAcceptedPeleSteps"][ind]
        dist = data.trajectory["distance0.5"][ind]
        bind = data.trajectory["Binding Energy"][ind]
        extract_snapshot_from_pdb(res_dir, simulation_folder, ids, position_num, mutation, step, dist, bind)


def extract_all(res_dir, data_dict, folders, cpus=24):
    """
    Extracts the top 10 distances for the 19 mutations at the same position

    Parameters
    ___________
    res_dir: str
       name of the results folder
    data_dict: dict
       A dictionary that contains SimulationData objects from the 19 simulation folders
    folders: str
       Path to the folder that has all the simulations at the same position
    cpus: int, optional
       How many cpus to paralelize the function

    """
    args = []
    for pele in glob("{}/PELE_*".format(folders)):
        name = basename(pele)[5:]
        output = basename(dirname(pele))
        args.append((pele, output, name))

    # parallelizing the function
    p = mp.Pool(cpus)
    func = partial(extract_10_pdb_single, res_dir=res_dir, data_dict=data_dict)
    p.map(func, args, 1)
    p.close()
    p.terminate()


def create_report(res_dir, mutation, position_num, output="summary", analysis="distance"):
    """
    Create pdf files with the plots of chosen mutations and the path to the

    Parameters
    ___________
    res_dir: str
       Name of the results folder
    mutation: dict
       A dictionary of SimulationData objects {key: SimulationData}
    position_num: str
       part of the path to the plots, the position that was mutated
    output: str, optional
       The pdf filename without the extension
    analysis: str, optional
       Type of the analysis (distance, binding or all)

    Returns
    _______
    name: str
       The path of the pdf file
    """
    pdf = FPDF()
    pdf.set_top_margin(17.0)
    pdf.set_left_margin(15.0)
    pdf.set_right_margin(15.0)
    pdf.add_page()

    # Title
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, "Best mutations in terms of distance and/or binding energy", align='C', ln=1)
    pdf.set_font('Arial', '', size=10)
    for key, val in mutation.items():
        dis = val.dist_diff.median()
        bind = val.bind_diff.median()
        message = 'Mutation {}: median distance increment {}, median binding energy increment {}'.format(key, dis, bind)
        pdf.ln(3)  # linebreaks
        pdf.cell(0, 5, message, ln=1)
    pdf.ln(8)  # linebreaks

    # box plots
    pdf.set_font('Arial', 'B', size=12)
    pdf.cell(0, 10, "Box plot of {}".format(analysis), align='C', ln=1)
    pdf.ln(8)
    if analysis == "distance":
        box1 = "{}_results/Plots/box/{}_distance.png".format(res_dir, position_num)
        pdf.image(box1, w=180)
        pdf.ln(1000000)
    elif analysis == "energy":
        box1 = "{}_results/Plots/box/{}_binding.png".format(res_dir, position_num)
        pdf.image(box1, w=180)
        pdf.ln(1000000)
    elif analysis == "all":
        box1 = "{}_results/Plots/box/{}_distance.png".format(res_dir, position_num)
        box2 = "{}_results/Plots/box/{}_binding.png".format(res_dir, position_num)
        pdf.image(box1, w=180)
        pdf.ln(5)
        pdf.image(box2, w=180)
        pdf.ln(1000000)

    # Plots
    pdf.set_font('Arial', 'B', size=12)
    pdf.cell(0, 10, "Scatter plots", align='C', ln=1)
    pdf.set_font('Arial', '', size=10)
    for mut, key in mutation.items():
        pdf.ln(3)
        pdf.cell(0, 10, "Plots {}".format(mut), ln=1)
        pdf.ln(3)
        plot1 = "{}_results/Plots/scatter_{}_{}/{}_{}.png".format(res_dir, position_num, "distance0.5", mut,
                                                                  "distance0.5")
        plot2 = "{}_results/Plots/scatter_{}_{}/{}_{}.png".format(res_dir, position_num, "sasaLig", mut, "sasaLig")
        plot3 = "{}_results/Plots/scatter_{}_{}/{}_{}.png".format(res_dir, position_num, "currentEnergy", mut,
                                                                  "currentEnergy")
        pdf.image(plot1, w=180)
        pdf.ln(3)
        pdf.image(plot2, w=180)
        pdf.ln(1000000)  # page break
        pdf.ln(3)
        pdf.image(plot3, w=180)
        pdf.ln(1000000)  # page break

    # Top poses
    pdf.set_font('Arial', 'B', size=12)
    pdf.cell(0, 10, "Path to the top poses", align='C', ln=1)
    pdf.set_font('Arial', size=10)
    pdf.ln(5)
    for mut, key in mutation.items():
        path = "{}_results/distances_{}/{}_pdbs".format(res_dir, position_num, mut)
        pdf.cell(0, 10, "{}: {} ".format(mut, abspath(path)), ln=1)
        pdf.ln(5)

    # Output report
    name = "{}_results/{}_{}.pdf".format(res_dir, output, position_num)
    pdf.output(name, 'F')
    return name


def find_top_mutations(res_dir, data_dict, position_num, output="summary", analysis="distance", thres=-0.1):
    """
    Finds those mutations that decreases the binding distance and binding energy and creates a report

    Parameters
    ___________
    res_dir: str
       Name of the results folder
    data_dict: dict
       A dictionary of SimulationData objects that holds information for all mutations
    position_num: str
       The position that was mutated
    output: str, optional
       Name of the reports created
    analysis: str, optional
       Choose between ("distance", "binding" or "all") to specify how to filter the mutations to keep
    thres: float, optional
       Set the threshold for those mutations to be included in the pdf
    """
    # Find top mutations
    logging.basicConfig(filename='{}_results/top_mutations.log'.format(res_dir), level=logging.DEBUG)
    count = 0
    mutation_dict = {}
    for key, value in data_dict.items():
        if "original" not in key:
            if analysis == "distance" and value.dist_diff.median() < thres:
                mutation_dict[key] = value
                count += 1
            elif analysis == "energy" and value.bind_diff.median() < thres:
                mutation_dict[key] = value
                count += 1
            elif analysis == "all" and value.dist_diff.median() < thres and value.bind_diff.median() < thres:
                mutation_dict[key] = value
                count += 1

    # Create a summary report with the top mutations
    if len(mutation_dict) != 0:
        logging.info(
            "{} mutations at position {} decrease {} by {} or less".format(count, position_num, analysis, thres))
        create_report(res_dir, mutation_dict, position_num, output, analysis)
    else:
        logging.warning("No mutations at position {} decrease {} by {} or less".format(position_num, analysis, thres))


def consecutive_analysis(file_name, dpi=800, box=30, traj=10, output="summary",
                         plot_dir=None, opt="distance", cpus=24, thres=-0.1):
    """
    Creates all the plots for the different mutated positions

    Parameters
    ___________
    file_name : str, iterable, directory
       A file, an iterable that contains the path to the PELE simulations folders or
       the path to the folders where the simulations are stored --> it is equivalent to dirname(iterable[0])
    dpi : int, optional
       The quality of the plots
    box : int, optional
       how many points are used for the box plots
    traj : int, optional
       how many top pdbs are extracted from the trajectories
    output : str, optional
       name of the output file for the pdfs
    plot_dir : str
       Name for the results folder
    opt : str, optional
       choose if to analyse distance, binding or all
    cpus : int, optional
       How many cpus to use to extract the top pdbs
    thres : float, optional
       The threshold for the mutations to be included in the pdf
    """
    if isfile(str(file_name)):
        with open("{}".format(file_name), "r") as pele:
            pele_folders = pele.readlines()
    elif isdir(str(file_name)):
        pele_folders = list(filter(isdir, os.listdir(file_name)))
        pele_folders = [join(file_name, folder) for folder in pele_folders]
    elif isiterable(file_name):
        pele_folders = file_name[:]
    else:
        raise Exception("No file or iterable passed")

    if not plot_dir:
        plot_dir = pele_folders[0].strip("\n")
        plot_dir = basename(dirname(plot_dir)).replace("_mutations", "")
    for folders in pele_folders:
        folders = folders.strip("\n")
        base = basename(folders)
        data_dict = analyse_all(folders, box=box, traj=traj)
        box_plot(plot_dir, data_dict, base, dpi)
        all_profiles(plot_dir, data_dict, base, dpi)
        extract_all(plot_dir, data_dict, folders, cpus=cpus)
        find_top_mutations(plot_dir, data_dict, base, output, analysis=opt, thres=thres)


def main():
    inp, dpi, box, traj, out, folder, analysis, cpus, thres = parse_args()
    consecutive_analysis(inp, dpi, box, traj, out, folder, analysis, cpus, thres)


if __name__ == "__main__":
    # Run this if this file is executed from command line but not if is imported as API
    main()
