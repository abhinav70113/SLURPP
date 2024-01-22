#!/bin/bash

# Edit: sing_image should be from the pulsarnet singularity image
sing_image=$1
data_dir=$2
code_dir=$3
dat_file=$4
flo=$5
fhi=$6
working_dir=$7
output_dir=${8}
segment=${9}
chunk=${10}
gpu_flag=${11}
sing_image_pulsarnet=${12}
pulsarnet_code_directory=${13}

inf_file=${dat_file::-4}.inf



# Check if the output file exists
base_name=$(basename "$dat_file")
file_string=$(echo "$base_name" | awk -F'_' '{print $1"_"$2"_"$3}')_${segment}_${chunk}
dm_value="DM${base_name##*DM}"; dm_value=${dm_value%.dat}
# Edit: Check if this is indeed the output format
output_search_file=${output_dir}/${file_string}_${dm_value}_PulsarNet.txt
# output_search_file=${output_dir}/${file_string}_${dm_value}_ACCEL_${zmax}.txtcand

if [ -s "$output_search_file" ]; then
    echo "Output File: $(basename $output_search_file) exists."
    if (( $(wc -l < "$output_search_file") > 0 )); then
        echo "Output File: $(basename $output_search_file) has more than zero lines, exiting with status 0."
        exit 0
    else
        echo "Output File: $(basename $output_search_file) is empty, continuing without processing."
    fi
fi

# file to store all periodicity search commands
#file_name=${file_string%_${segment}_${chunk}}.sh

#Cleaning up any prior runs
rm -rf $working_dir

mkdir -p $working_dir
mkdir -p $output_dir

## Copy the *.dat and *.inf file to the working directory 
# rsync -Pav $dat_file $working_dir 
# rsync -Pav $inf_file $working_dir

basename_inf=$(basename "$inf_file")
basename_dat=$(basename "$dat_file")

if [ $segment != "full" ]; then
    
    # Edit: maybe put these in double quotes
    new_dat_file=${dat_file//full/$segment}
    new_dat_file=${new_dat_file//ck00/$chunk}
    new_inf_file=${inf_file//full/$segment}
    new_inf_file=${new_inf_file//ck00/$chunk}

    # Check if the new_dat_file and new_inf_file exist
    if [[ ! -e $new_dat_file ]]; then
        echo "Error: $new_dat_file does not exist" >&2
        rsync -Pav $dat_file $working_dir 
        rsync -Pav $inf_file $working_dir
        echo "Splitting the dat file"
        singularity exec -H $HOME:/home1 -B $data_dir:$data_dir $sing_image python ${code_dir}/split_datfiles.py -i $basename_dat -c $chunk -s $segment -w $working_dir
        status=$?
        if [ $status -ne 0 ]; then
            echo "Error in split_datfiles.py"
            echo "Cleaning up"
            rm -rf $working_dir
            exit 1
        fi
    else
        echo "Input File: $(basename $new_dat_file) exists."
        rsync -Pav $new_dat_file $working_dir
        rsync -Pav $new_inf_file $working_dir
    fi

    basename_dat=${basename_dat/full/$segment}
    basename_dat=${basename_dat/ck00/$chunk}
    
    dat_file=$new_dat_file
    inf_file=$new_inf_file
    
else
    rsync -Pav $dat_file $working_dir 
    rsync -Pav $inf_file $working_dir
fi

# Parse the *.err and *.out file from the dat_file
# Split the path into an array based on '/'
IFS='/' read -r -a path_array <<< "$dat_file"

# Extract the filename
filename="${path_array[-1]}"

# Insert 'PN' after the first underscore and change the extension to .err
# Extract the part before the first underscore
first_part="${filename%%_*}"
# Extract the rest of the filename after the first underscore
rest="${filename#*_}"
# Reconstruct the filename
new_filename_err="${first_part}_PN_${rest%.*}.err"
new_filename_out="${first_part}_PN_${rest%.*}.out"

# Reconstruct the new log file path
log_file_err="/${path_array[1]}/${path_array[2]}/${path_array[3]}/${path_array[4]}/${path_array[5]}/${path_array[6]}/${path_array[7]}/00_SLURM_JOB_LOGS/${new_filename_err}"
log_file_out="/${path_array[1]}/${path_array[2]}/${path_array[3]}/${path_array[4]}/${path_array[5]}/${path_array[6]}/${path_array[7]}/00_SLURM_JOB_LOGS/${new_filename_out}"

if [[ $gpu_flag -eq 1 ]]; then
# Edit: The output of periodicity_search_pulsarnet.py is not being redirected to the log files somehow
    singularity exec --nv -H $HOME:/home1 -B $data_dir:$data_dir $sing_image_pulsarnet python ${code_dir}/periodicity_search_pulsarnet.py -i $basename_dat -s $flo -e $fhi -t $working_dir -C $pulsarnet_code_directory -P $sing_image_pulsarnet -D $data_dir --log_out $log_file_out --log_err $log_file_err >> $log_file_out 2>> $log_file_err
    status=$?
    if [ $status -ne 0 ]; then
        echo "Error in periodicity_search_pulsarnet.py"
        echo "Cleaning up"
        rm -rf $working_dir
        exit 1
    fi
else
# Edit: The output of periodicity_search_pulsarnet.py is not being redirected to the log files somehow
    singularity exec --nv -H $HOME:/home1 -B $data_dir:$data_dir $sing_image_pulsarnet python ${code_dir}/periodicity_search_pulsarnet.py -i $basename_dat -s $flo -e $fhi -t $working_dir -C $pulsarnet_code_directory -P $sing_image_pulsarnet -D $data_dir -g --log_out $log_file_out --log_err $log_file_err >> $log_file_out 2>> $log_file_err
    status=$?
    if [ $status -ne 0 ]; then
        echo "Error in periodicity_search_pulsarnet.py"
        echo "Cleaning up"
        rm -rf $working_dir
        exit 1
    fi

fi

#Copy the output files to the output directory
rsync -Pav $working_dir/*PulsarNet.txt  $output_dir
rsync -Pav $working_dir/*.inf  $output_dir
#Copy back also data files if they were split

# if [ $segment != "full" ]; then
#     rsync -Pav $working_dir/*.dat  $output_dir
# fi

# if [[ $wmax -eq 0 ]]; then
#     base_file1="${file_string}_${dm_value}_ACCEL_${zmax}.txtcand"
#     base_file2="${file_string}_${dm_value}.inf"
#     base_file3="${file_string}_${dm_value}_ACCEL_${zmax}"
#     base_file4="${file_string}_${dm_value}_ACCEL_${zmax}.cand"
# else
#     base_file1="${file_string}_${dm_value}_ACCEL_${zmax}_JERK_${wmax}.txtcand"
#     base_file2="${file_string}_${dm_value}.inf"
#     base_file3="${file_string}_${dm_value}_ACCEL_${zmax}_JERK_${wmax}"
#     base_file4="${file_string}_${dm_value}_ACCEL_${zmax}_JERK_${wmax}.cand"
# fi

# #Group 1 is for the case when accel search finds no candidates and only outputs an empty .txtcand file

# expected_files_group1=("$working_dir/$base_file1" "$working_dir/$base_file2")
# expected_files_group2=("$working_dir/$base_file3" "$working_dir/$base_file4")

# # Rsync files from group1
# for file in "${expected_files_group1[@]}"; do
#     echo rsync -Pav "$file" "$output_dir/"
#     rsync -Pav "$file" "$output_dir/"
#     status=$?
#     if [ $status -ne 0 ]; then
#         echo "Error: rsync of $(basename $file) failed" >&2
#         exit 1
#     fi
# done

# # Check the .txtcand file and rsync files from group2 if necessary
# txtcand_file="$working_dir/$base_file1"
# if (( $(wc -l < "$txtcand_file") > 0 )); then
#     for file in "${expected_files_group2[@]}"; do
#         echo rsync -Pav "$file" "$output_dir/"
#         rsync -Pav "$file" "$output_dir/"
#         status=$?
#         if [ $status -ne 0 ]; then
#             echo "Error: rsync of $(basename $file) failed" >&2
#             exit 1
#         fi
#     done
# fi

# Clean Up
rm -rf $working_dir

# expected_files_group1=("$output_dir/$base_file1" "$output_dir/$base_file2")
# expected_files_group2=("$output_dir/$base_file3" "$output_dir/$base_file4")


# # Check if the expected output files exist 
# all_files_exist_in_group1=true
# for file in "${expected_files_group1[@]}"; do
#     if [[ ! -e $file ]]; then
#         echo "Error: Output file $file does not exist" >&2
#         all_files_exist_in_group1=false
#         break
#     else
#         echo "Output File: $(basename $file) exists."
#     fi
# done

# if [[ $all_files_exist_in_group1 == true ]]; then
#     txtcand_file="$output_dir/${file_string}_${dm_value}_ACCEL_${zmax}.txtcand"
#     if (( $(wc -l < "$txtcand_file") > 0 )); then
#         echo "Output File: $(basename $txtcand_file) exists and is not empty, so checking for the search candidates file."
#         for file in "${expected_files_group2[@]}"; do
#             if [[ ! -e $file ]]; then
#                 echo "Error: Expected output file $file from group 2 does not exist" >&2
#                 exit 1
#             else
#                 echo "Output File: $(basename $file) exists."
#             fi
#         done
#     fi
# else
#     exit 1
# fi





