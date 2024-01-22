from joblib import Parallel, delayed
import subprocess
import sys, os, argparse, errno
import numpy as np
#from pulsar_miner import Observation

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def periodicity_search_pulsarnet(data,flo,fhi,working_dir,pulsarnet_code_dir, sing_image_pulsarnet, data_dir, log_out, log_err,remove_fft_files=True, remove_dat_files=True, accel_search_gpu_flag=True):
    os.chdir(working_dir)
    # Process only .dat files for now
    if data.endswith('.fft'):
        #print('Cant process .fft files. Please provide .dat files')
        #print to terminal
        subprocess.check_output('echo Cant process .fft files. Please provide .dat files', shell=True)
        sys.exit(1)
        # realfft_cmd = 'realfft %s' % data
        # subprocess.check_output(realfft_cmd, shell=True)
        
        # data = data.replace('.dat', '.fft')
    # Edit: incorporte the GPU flag information here. Tell the user if the program is running on CPU or GPU
    #check if path exists
    main_py_path = os.path.join(pulsarnet_code_dir, 'main.py')
    if os.path.exists(main_py_path):
        #print('PulsarNet code path exists')
        subprocess.check_output('echo PulsarNet code path exists', shell=True)
        #print('Running Accel Search using PulsarNet on %s using CPUs' % (data))
        subprocess.check_output('echo Running Accel Search using PulsarNet on %s using CPUs' % (data), shell=True)

        #Check if the data file exists
        if not os.path.exists(data):
            #print('Data file does not exist')
            subprocess.check_output('echo Data file does not exist', shell=True)
            sys.exit(1)
        else:
            #print('Data file exists')
            subprocess.check_output('echo Data file exists', shell=True)


        sing_prefix = ''#'singularity exec --nv -H $HOME:/home1 -B %s:%s %s ' % (data_dir, data_dir, sing_image_pulsarnet)
        # Edit: currently the models are loaded from the directory PulsarNet in scratch, will probably make sense to rsync the models as well. 
        # Edit: Implement giving the models as an argument to the main script instead of hardcoding the path in the config file.
        if (log_out is not None) and (log_err is not None):
            pulsarnet_search_cmd = 'python %s -s %d -e %d -o %s %s >> %s 2>> %s' % (main_py_path, flo,fhi, data[:-4], data, log_out, log_err) #Output label is the same as data file without .dat
            #print(pulsarnet_search_cmd)
            subprocess.check_output(sing_prefix+pulsarnet_search_cmd, shell=True)
        else:
            #print('No log files provided. Stdout and Stderr will not be piped')
            subprocess.check_output('echo No log files provided. Stdout and Stderr will not be piped', shell=True)
            pulsarnet_search_cmd = 'python %s -s %d -e %d -o %s %s' % (main_py_path, flo,fhi, data[:-4], data)
            print(pulsarnet_search_cmd)
            subprocess.check_output(sing_prefix+pulsarnet_search_cmd, shell=True)
        
    else:
        #print('PulsarNet code path does not exist')
        subprocess.check_output('echo PulsarNet code path does not exist', shell=True)
        sys.exit(1)
    
    # Edit: An fft file is never expected
    if remove_fft_files:
      os.remove(data)
    if remove_dat_files:
      os.remove(data.replace('.fft', '.dat'))
    

    
    


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run PulsarNet Search one CPU per job')
    parser.add_argument('-i', '--input', help='Input Data (Presto *dat/.fft file)', required=True)
    parser.add_argument('-s', '--flo', help='lowest value of frequency to search', type=float, default=40.0)
    parser.add_argument('-e', '--fhi', help='highest value of frequency to search', type=float, default=1000.0)
    parser.add_argument('-t', '--tmp_working_dir', help='TMP Working dir where do the processing', type=str, default='/tmp')
    parser.add_argument('-C','--pulsarnet_code_dir', help='Path to PulsarNet code directory', type=str, required=True)
    parser.add_argument('-P','--sing_image_pulsarnet', help='Path to PulsarNet singularity image', type=str, required=True)
    parser.add_argument('-D','--data_dir', help='Data_dir like /hercules', type=str, required=True)
    parser.add_argument("-g", "--gpu_flag", dest="gpu_flag", action='store_false', default=True, help="If you set this flag, code will disable GPU for accelsearch. Default is True.")
    parser.add_argument("--log_out", dest="log_out", default=None, help="pipe the Stdout to this file. Default is current directory.")
    parser.add_argument("--log_err", dest="log_err", default=None, help="pipe the Stderr to this file. Default is current directory.")
    
    args = parser.parse_args()

    data = args.input
    flo = args.flo
    fhi = args.fhi
    gpu_flag = args.gpu_flag
    basename = os.path.basename(data)[:-4]
    cluster = basename.split('_')[0]
    epoch = basename.split('_')[1]
    beam = basename.split('_')[2]
    pulsarnet_code_dir = args.pulsarnet_code_dir
    sing_image_pulsarnet = args.sing_image_pulsarnet
    data_dir = args.data_dir
    log_out = args.log_out
    log_err = args.log_err

    working_dir = args.tmp_working_dir
    mkdir_p(working_dir)
    
    # Edit: fft and dat delete flags are set to False here. There wont be any fft files created by pulsarnet, so do not comment out the fft flag
    periodicity_search_pulsarnet(data, flo, fhi, working_dir, pulsarnet_code_dir, sing_image_pulsarnet, data_dir, log_out,log_err,remove_fft_files=False, remove_dat_files=True, accel_search_gpu_flag=gpu_flag)
