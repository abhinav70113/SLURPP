# **SLURM PULSARMINER PULSARNET**
This repository contains the necessary files to run PulsarNet on a HPC cluster using SLURM. Forked originally from [SLURM Pulsarminer](https://github.com/vishnubk/SLURM_PULSARMINER.git)

# **SLURM Pulsarminer: Streamlined Binary Pulsar Search Processing**

**SLURM Pulsarminer**, is an efficient tool to facilitate the operation of the software Pulsarminer on High-Performance Computing (HPC) clusters. 

It is currently compatibile with **Pulsarminer version 1.1.5 (08Jun2020)** and **PRESTO2**. It supports AccelSearch on CPU/GPU and Jerk Search on CPU. It requires a Singularity image with the necessary software installed.

## Why SLURM Pulsarminer?

Designed for those who need to process certain beams prior to others, **SLURM Pulsarminer** offers the ability to intelligently divide your dedispersion, segmented and full length acceleration, jerk search, and folding trials for efficient parallel execution. For example, it significantly expedites the analysis of the central beam in a Globular Cluster observation before other beams.

Many of the core routines are predominantly sourced from **PRESTO** or **Pulsarminer**.

## Getting Started

Follow the steps below to initiate **SLURM Pulsarminer**:

1. Modify your standard Pulsarminer config file. For reference, view the example in "sample_M30.config".

2. Adjust the "slurm_config.cfg" to match your cluster's specifications. Remember to include the absolute path of your Singularity image and specific mount paths for your data.

3. Execute the SLURM Pulsarminer launcher script with your Pulsarminer config file and your observation file. 

   Note: It's advised to execute this script within a tmux or screen session for uninterrupted operations since you will be launching hundreds to thousands of job per observation depending on your search range.

## LAUNCH_SLURM_PULSARMINER.sh Usage Guide

Fill the SLURM config file carefully, reflecting your system's specifications.

### Usage:

```bash
./LAUNCH_SLURM_PULSARMINER.sh [-h] [-m max_slurm_jobs] [-o observation_file] [-p config_file] [-t tmp_directory]
```

### Options:

- **-h**          Displays this help message and exits
- **-m NUM**      Sets the maximum number of SLURM jobs to submit at a time (default: five less than your max jobs you can submit)
- **-o FILE**     Defines the observation file to process
- **-p FILE**     Specifies the Pulsarminer configuration file to use
- **-t DIR**      Indicates the temporary directory (default: /tmp)

## Future Edits

These edits will be performed in the near future. Before running the code, watch out for these:
### **create_slur_jobs_pulsarnet.py**
1. Line 377: Edit: For Pulsarnet, I will try implementing the logic that if a gpu is not available then run on cpu.
2. Line 385: Edit: Try accepting these pulsarnet parameters from the pm_config file.
3. Multiple lines: Edit: Create a slurm job for accel search, right now just do it with CPU, implement GPU later.
### **PERIODICITY_SEARCH_AND_COPY_BACK_PULSARNET.sh**
1. Line 56: Edit: maybe put these in double quotes
2. Line 114: Edit: The output of periodicity_search_pulsarnet.py is not being redirected to the log files somehow
### **periodicity_search_pulsarnet.py**
1. Line 28: # Edit: incorporte the GPU flag information here. Tell the user if the program is running on CPU or GPU
2. Line 48: # Edit: currently the models are loaded from the directory PulsarNet in scratch, will probably make sense to rsync the models as well. 
3. Line 49: # Edit: Implement giving the models as an argument to the main script instead of hardcoding the path in the config file.
4. Line 66,109:  # Edit: An fft file is never expected

## Known Bugs
1. 'ACCELSEARCH_GPU_LIST_ZMAX' and 3 more options aren't recognized flag in pm_config parser at all 
2. The number of DM trials in the Dedispersion script and the create_slurm_jobs_pulsarnet are different. One is hardcoded to be in steps on 0.05 and the other in linspaced with dedisp_cpu_cores. This might result in problems with dedispersion and time wasting operations.
3. The directory /tmp/abhinav must be given as a flag as well as in the config file 
4. Verbosity level cant be given explicitly from the lauch script 
5. There is no functionality to see the progress bar of how many accel search files have been completed 
6. CandyJar bug: pics_meerkat_l_sband_combined_best_recall,pics_palfa_meerkat_l_sband_best_fscore 

        

## Additional Resources

Should you prefer using the original repositories of PULSARMINER or PRESTO, find them here:

- [PULSARMINER](https://github.com/alex88ridolfi/PULSAR_MINER)
- [PRESTO](https://github.com/scottransom/presto)


Happy processing!
