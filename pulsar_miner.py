#!/usr/bin/env python2
#################### ALESSANDRO RIDOLFI ########################S


import sys, os, os.path, glob, subprocess, multiprocessing, shlex, shutil, copy
import random, time, datetime, gc, imp
import numpy as np

import psrfits    #From PRESTO
import filterbank #From PRESTO
import rfifind    #From PRESTO
import sifting    #From PRESTO
import infodata   #From PRESTO
import parfile    #From PRESTO
import psr_utils  #From PRESTO

import warnings
from multiprocessing.pool import ThreadPool

warnings.simplefilter('ignore', UserWarning)

string_version = "1.1.5 (08Jun2020)"


class Pulsar(object):
        def __init__(self, parfilename):
                LIGHT_SPEED = 2.99792458e10   # Light speed in CGS units
                
                pulsar_parfile = parfile.psr_par(parfilename)

                self.parfilename = parfilename
                if hasattr(pulsar_parfile, 'PSR'):
                        self.psr_name = pulsar_parfile.PSR
                elif hasattr(pulsar_parfile, 'PSRJ'):
                        self.psr_name = pulsar_parfile.PSRJ

                self.PEPOCH = pulsar_parfile.PEPOCH
                self.F0 = pulsar_parfile.F0
                self.P0_s = 1./self.F0
                self.P0_ms = self.P0_s * 1000
                if hasattr(pulsar_parfile, 'F1'):
                        self.F1 = pulsar_parfile.F1
                else:
                        self.F1 = 0
                if hasattr(pulsar_parfile, 'F2'):
                        self.F2	= pulsar_parfile.F2
		else:
                        self.F2 = 0

                self.is_binary = hasattr(pulsar_parfile, 'BINARY')
                

                if self.is_binary:
                        self.pulsar_type = "binary"
                        self.binary_model    = pulsar_parfile.BINARY

                        # 1) Orbital period
                        if hasattr(pulsar_parfile, 'PB'):
                                self.Pb_d            = pulsar_parfile.PB
                                self.Pb_s            = self.Pb_d*86400
                                self.Fb0             = 1./self.Pb_s
                        elif hasattr(pulsar_parfile, 'FB0'):
                                self.Fb0       = pulsar_parfile.FB0
                                self.Pb_s      = 1./self.Fb0
                                self.Pb_d      = self.Pb_s / 86400.

                        # 2) Projected semi-major axis of the pulsar orbit
                        self.x_p_lts           = pulsar_parfile.A1
                        self.x_p_cm            = pulsar_parfile.A1 * LIGHT_SPEED

                        # 3) Orbital eccentricity
                        if hasattr(pulsar_parfile, 'E'):
                                self.ecc       = pulsar_parfile.E
                        elif hasattr(pulsar_parfile, 'ECC'):
                                self.ecc       = pulsar_parfile.ECC
                        elif hasattr(pulsar_parfile, 'EPS1') and hasattr(pulsar_parfile, 'EPS2'):
                                self.eps1      = pulsar_parfile.EPS1
                                self.eps2      = pulsar_parfile.EPS2
				self.ecc       = np.sqrt(self.eps1**2  + self.eps2**2)
                        else:
                                self.ecc       = 0 
                                
                        # 4) Longitude of periastron
                        if hasattr(pulsar_parfile, 'OM'):
                                self.omega_p_deg  = pulsar_parfile.OM
                        else:
                                self.omega_p_deg  = 0
                        self.omega_p_rad  = self.omega_p_deg * np.pi/180


                        # 5) Epoch of passage at periastron/ascending node
                        if hasattr(pulsar_parfile, 'T0'):
                                self.T0           = pulsar_parfile.T0
                                self.Tasc         = self.T0
                        elif hasattr(pulsar_parfile, 'TASC'):
                                self.Tasc         = pulsar_parfile.TASC
                                self.T0           = self.Tasc

                                
                        self.v_los_max = (2*np.pi * self.x_p_cm / self.Pb_s)
                        self.doppler_factor = self.v_los_max / LIGHT_SPEED

                else:
                        # If the pulsar is isolated
                        self.pulsar_type = "isolated"
                        self.v_los_max = 0
                        self.doppler_factor = 1e-4  # Account for Doppler shift due to the Earth motion around the Sun


                                

def check_if_cand_is_known(candidate, list_known_pulsars, numharm):
        #Loop over all the known periods of the pulsars in the cluster
        P_cand_ms = candidate.p * 1000
        BOLD = '\033[1m'
        END  = '\033[0m'
    
        for i in range(len(list_known_pulsars)):
                psrname = list_known_pulsars[i].psr_name
                
                P_ms = list_known_pulsars[i].P0_ms
                P_ms_min = P_ms * (1 - list_known_pulsars[i].doppler_factor)
                P_ms_max = P_ms * (1 + list_known_pulsars[i].doppler_factor)

                if (P_cand_ms > P_ms_min) and (P_cand_ms < P_ms_max):
                        #print "%sP_min = %.6f ms < %.6f < %.6f ms = P_max    --> ALREADY KNOWN: PSR %s !!%s" % (BOLD, P_ms_min, P_cand_ms, P_ms_max, psrname, END)
                        str_harm = "Fundamental (%.7f ms)" % (P_ms)
                        return True, psrname, str_harm

                else:
                        #print "----------------- HARMONICS ----"
                        for nh in range(1, numharm + 1):
                                for n in range(1,16+1):
                                        P_known_ms_nh_min = P_ms_min * (np.float(n)/ nh)
                                        P_known_ms_nh_max = P_ms_max * (np.float(n)/ nh)
                
                                        #print "nh = %d/%d  --> Pulsar %s (P=%.10f) has a period = %.10f - %.10f  (cand = %.10f)" % (nh, n, psrname, P_ms, P_known_ms_nh_min, P_known_ms_nh_max, P_cand_ms)

                                        if (P_cand_ms >= P_known_ms_nh_min) and (P_cand_ms <= P_known_ms_nh_max):
                                                #print "%sARGH! Candidate with P = %.10f ms is the %d/%d-th harmonic of pulsar %s (P = %.10f ms)%s" % (BOLD, P_cand_ms, nh, n, psrname, P_ms, END)
                                                str_harm = "%d/%d of %.7f ms" % ( n, nh, P_ms)
                                                return True, psrname, str_harm

                
                        #print "----------------- SUBHARMONICS ----"
                        for ns in range(2, numharm + 1):
                                for n in range(1,16+1):
                                        P_known_ms_ns_min = P_ms_min * (np.float(ns) / n)
                                        P_known_ms_ns_max = P_ms_max * (np.float(ns) / n)
                                        #print "ns = %d/%d  --> Pulsar %s (P=%.10f) has a period = %.10f - %.10f (cand = %.10f)" % (n, ns, psrname, P_ms, P_known_ms_ns_min, P_known_ms_ns_max, P_cand_ms) 

                                        if (P_cand_ms >= P_known_ms_ns_min) and (P_cand_ms <= P_known_ms_ns_max):
                                                #print "%sARGH! Candidate with P = %.10f ms is the %d/%d-th subharmonic of pulsar %s (P = %.10f ms%s)" % (BOLD, P_cand_ms, n, ns, psrname, P_ms, END)
                                                str_harm = "%d/%d of %.7f ms" % ( ns, n, P_ms)
                                                return True, psrname, str_harm
                                        
        return False, "", ""

                        
                
class Inffile(object):
        def __init__(self, inffilename):
                inffile = open(inffilename, "r")
                for line in inffile:
                        if "Data file name without suffix" in line:
                                self.datafilebasenam = line.split("=")[-1].strip()
                        elif "Telescope used" in line:
                                self.telescope = line.split("=")[-1].strip()
                        elif "Instrument used" in line:
                                self.instrument = line.split("=")[-1].strip()
                        elif "Object being observed" in line:
                                self.source = line.split("=")[-1].strip()
                        elif "J2000 Right Ascension" in line:
                                self.RAJ = line.split("=")[-1].strip()
                        elif "J2000 Declination" in line:
                                self.DECJ = line.split("=")[-1].strip()
                        elif "Data observed by" in line:
                                self.observer = line.split("=")[-1].strip()
                        elif "Epoch of observation" in line:
                                self.start_MJD = np.float128(line.split("=")[-1].strip())
                        elif "Barycentered?" in line:
                                self.barycentered = int(line.split("=")[-1].strip())
                        elif "Number of bins in the time series" in line:
                                self.nsamples = int(line.split("=")[-1].strip())
                        elif "Width of each time series bin" in line:
                                self.tsamp_s = np.float128(line.split("=")[-1].strip())
                        elif "Any breaks in the data?" in line:
                                self.breaks_in_data = int(line.split("=")[-1].strip())
                        elif "Type of observation" in line:
                                self.obstype = line.split("=")[-1].strip()
                        elif "Beam diameter" in line:
                                self.beamdiameter = np.float128(line.split("=")[-1].strip())
                        elif "Dispersion measure" in line:
                                self.DM = np.float128(line.split("=")[-1].strip())
                        elif "Central freq of low channel" in line:
                                self.freq_ch1 = np.float128(line.split("=")[-1].strip())
                        elif "Total bandwidth" in line:
                                self.bw = np.float128(line.split("=")[-1].strip())
                        elif "Number of channels" in line:
                                self.nchan = int(line.split("=")[-1].strip())
                        elif "Channel bandwidth" in line:
                                self.bw_chan = np.float128(line.split("=")[-1].strip())
                        elif "Data analyzed by" in line:
                                self.analyzer = line.split("=")[-1].strip()
                inffile.close()
        

class Observation(object):
        def __init__(self, file_name, data_type="psrfits", verbosity_level=1):
                self.file_abspath = os.path.abspath(file_name)
                self.file_nameonly = self.file_abspath.split("/")[-1]
                self.file_basename, self.file_extension = os.path.splitext(self.file_nameonly)
                
                if data_type=="filterbank":

                        try:
                                object_file = filterbank.FilterbankFile(self.file_abspath)

                                self.N_samples        = object_file.nspec
                                self.t_samp_s         = object_file.dt
                                self.T_obs_s          = self.N_samples * self.t_samp_s
                                self.nbits            = object_file.header['nbits']
                                self.nchan            = object_file.nchan
                                self.chanbw_MHz       = object_file.header['foff']
                                self.bw_MHz           = self.nchan * self.chanbw_MHz
                                self.freq_central_MHz = object_file.header['fch1'] + object_file.header['foff']*0.5*object_file.nchan
                                self.freq_high_MHz    = np.amax(object_file.freqs)
                                self.freq_low_MHz     = np.amin(object_file.freqs)
                                self.MJD_int          = int(object_file.header['tstart'])
                                self.Tstart_MJD       = object_file.header['tstart']
                                
                                self.source_name      = object_file.header['source_name'].strip()
                                

                        except ValueError:
                                if verbosity_level >= 1:
                                        print "WARNING: I got a Value Error! Likely your filterbank data is not 8-,16- or 32-bit. Using 'header' to get the necessary information..."

                                self.N_samples        = np.abs(int(    get_command_output("header %s -nsamples" % (self.file_abspath)).split()[-1]  ))
                                self.t_samp_s         = np.float(      get_command_output("header %s -tsamp"    % (self.file_abspath)).split()[-1]) *1.0e-6
                                self.T_obs_s          = np.float(      get_command_output("header %s -tobs"     % (self.file_abspath)).split()[-1])
                                self.nbits            = int(           get_command_output("header %s -nbits"    % (self.file_abspath)).split()[-1])
                                self.nchan            = int(           get_command_output("header %s -nchans"   % (self.file_abspath)).split()[-1])
                                self.chanbw_MHz       = np.fabs(np.float(       get_command_output("header %s -foff"     % (self.file_abspath)).split()[-1]))
                                self.bw_MHz           = self.chanbw_MHz*self.nchan
                                self.backend          = get_command_output("header %s -machine" % (self.file_abspath)).split()[-1]
                                self.Tstart_MJD              = np.float(      get_command_output("header %s -tstart"   % (self.file_abspath)).split()[-1])
                                self.freq_high_MHz    = np.float(      get_command_output("header %s -fch1"     % (self.file_abspath)).split()[-1]) + 0.5*self.chanbw_MHz
                                self.freq_central_MHz = self.freq_high_MHz -0.5*self.bw_MHz
                                self.freq_low_MHz     = self.freq_high_MHz - self.bw_MHz

                                print self.N_samples, self.t_samp_s, self.T_obs_s, self.nbits, self.nchan, self.chanbw_MHz, self.bw_MHz, self.backend, self.Tstart_MJD, self.freq_high_MHz, self.freq_central_MHz, self.freq_low_MHz
                                
                                
                if data_type=="psrfits":
                        if verbosity_level >= 2:
                                print "Reading PSRFITS...."
                        if psrfits.is_PSRFITS(file_name) == True:
                                if verbosity_level >= 2:
                                        print "File '%s' correctly recognized as PSRFITS" % (file_name)
                                object_file = psrfits.PsrfitsFile(self.file_abspath)
                                self.bw_MHz           = object_file.specinfo.BW
                                self.N_samples        = object_file.specinfo.N
                                self.T_obs_s          = object_file.specinfo.T
                                self.backend          = object_file.specinfo.backend
                                self.nbits            = object_file.specinfo.bits_per_sample
                                self.date_obs         = object_file.specinfo.date_obs
                                self.dec_deg          = object_file.specinfo.dec2000
                                self.dec_str          = object_file.specinfo.dec_str
                                self.chanbw_MHz       = object_file.specinfo.df
                                self.t_samp_s         = object_file.specinfo.dt
                                self.freq_central_MHz = object_file.specinfo.fctr
                                self.receiver         = object_file.specinfo.frontend
                                self.freq_high_MHz    = object_file.specinfo.hi_freq
                                self.freq_low_MHz     = object_file.specinfo.lo_freq
                                self.MJD_int          = object_file.specinfo.mjd
                                self.MJD_sec          = object_file.specinfo.secs
                                self.Tstart_MJD       = self.MJD_int + np.float(self.MJD_sec/86400.)
                                self.nchan            = object_file.specinfo.num_channels
                                self.observer         = object_file.specinfo.observer
                                self.project          = object_file.specinfo.project_id
                                self.ra_deg           = object_file.specinfo.ra2000
                                self.ra_str           = object_file.specinfo.ra_str
                                self.seconds_of_day   = object_file.specinfo.secs
                                self.source_name      = object_file.specinfo.source
                                self.telescope        = object_file.specinfo.telescope

                        else:
                                print "Reading PSRFITS (header only)...."
                                self.bw_MHz           = np.float(get_command_output("vap -n -c bw %s" % (file_name)).split()[-1])
                                self.N_samples        = np.float(get_command_output_with_pipe("readfile %s" % (file_name), "grep Spectra").split("=")[-1])
                                self.T_obs_s          = np.float(get_command_output("vap -n -c length %s" % (file_name)).split()[-1])
                                self.backend          = get_command_output("vap -n -c backend %s" % (file_name)).split()[-1]
                                self.nbits            = int(get_command_output_with_pipe("readfile %s" % (file_name), "grep bits").split("=")[-1])
                                self.chanbw_MHz       = np.float(get_command_output_with_pipe("readfile %s" % (file_name), "grep Channel").split("=")[-1])
                                self.t_samp_s         = np.float(get_command_output("vap -n -c tsamp %s" % (file_name)).split()[-1])
                                self.freq_central_MHz = np.float(get_command_output("vap -n -c freq %s" % (file_name)).split()[-1])
                                self.receiver         = get_command_output("vap -n -c rcvr %s" % (file_name)).split()[-1]
                                self.freq_high_MHz    = np.float(get_command_output_with_pipe("readfile %s" % (file_name), "grep High").split("=")[-1])
                                self.freq_low_MHz     = np.float(get_command_output_with_pipe("readfile %s" % (file_name), "grep Low").split("=")[-1])
                                self.nchan            = int(get_command_output("vap -n -c nchan %s" % (file_name)).split()[-1])
                                self.MJD_int          = int(get_command_output("psrstat -Q -c ext:stt_imjd %s" % (file_name)).split()[-1])
                                self.MJD_sec_int      = int(get_command_output("psrstat -Q -c ext:stt_smjd %s" % (file_name)).split()[-1])
                                self.MJD_sec_frac     = np.float(get_command_output("psrstat -Q -c ext:stt_offs %s" % (file_name)).split()[-1])
                                self.MJD_sec          = self.MJD_sec_int + self.MJD_sec_frac
                                self.Tstart_MJD       = self.MJD_int + np.float(self.MJD_sec/86400.) 


def execute_and_log(command, work_dir, log_abspath, dict_envs={}, flag_append=0, verbosity_level=0):
        datetime_start = (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M")
        time_start = time.time()
        if flag_append == 1:
                flag_open_mode = "a"
        else:
                flag_open_mode = "w+"
        log_file = open("%s" % (log_abspath), flag_open_mode)
        executable = command.split()[0]
        

        log_file.write("****************************************************************\n")
        log_file.write("START DATE AND TIME: %s\n" % (datetime_start))
        log_file.write("\nCOMMAND:\n")
        log_file.write("%s\n\n" % (command))
        log_file.write("WORKING DIRECTORY: %s\n" % (work_dir))
        log_file.write("****************************************************************\n")
        log_file.flush()
        

        list_for_Popen = command.split()
        env_subprocess = os.environ.copy()
        if dict_envs: #If the dictionary is not empty                                                                                                                                                            
                for k in dict_envs.keys():
                        env_subprocess[k] = dict_envs[k]
        
        proc = subprocess.Popen(list_for_Popen, stdout=log_file, stderr=log_file, cwd=work_dir, env=env_subprocess)
        proc.communicate()  #Wait for the process to complete                                                                                                                                                    

        datetime_end = (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M")
        time_end = time.time()

        if verbosity_level >= 1:
                print "execute_and_log:: COMMAND: %s" % (command)
                print "execute_and_log:: which %s: "% (executable), get_command_output("which %s" % (executable))
                print "execute_and_log:: WORKING DIRECTORY = ", work_dir
                print "execute_and_log:: CHECK LOG WITH: \"tail -f %s\"" % (log_abspath); sys.stdout.flush()
                print "execute_and_log: list_for_Popen = ", list_for_Popen
                print "execute_and_log: log_file       = ", log_file
                print "execute_and_log: env_subprocess = ", env_subprocess

        log_file.write("\nEND DATE AND TIME: %s\n" % (datetime_end))
        log_file.write("\nTOTAL TIME TAKEN: %d s\n" % (time_end - time_start))
        log_file.close()



def sift_candidates(work_dir, LOG_basename, LOG_dir,  dedispersion_dir, observation_basename, segment_label, chunk_label, list_zmax, jerksearch_zmax, jerksearch_wmax, flag_remove_duplicates, flag_DM_problems, flag_remove_harmonics, minimum_numDMs_where_detected, minimum_acceptable_DM=2.0, period_to_search_min_s=0.001, period_to_search_max_s=15.0, verbosity_level=0 ):
        work_dir_basename = os.path.basename(work_dir)
        string_ACCEL_files_dir = os.path.join(dedispersion_dir, observation_basename, segment_label, chunk_label)
        best_cands_filename = "%s/best_candidates_%s.siftedcands" % (work_dir, work_dir_basename)
        if verbosity_level >= 3:
                print "sift_candidates:: best_cands_filename = %s" % (best_cands_filename)
                print "sift_candidates:: string_ACCEL_files_dir = %s" % (string_ACCEL_files_dir)
        
        list_ACCEL_files = []
        for z in list_zmax:
                string_glob = "%s/*ACCEL_%d" % (string_ACCEL_files_dir, z)
                if verbosity_level >= 1:    print "Reading files '%s'..." % (string_glob),
                list_ACCEL_files = list_ACCEL_files + glob.glob(string_glob)
                if verbosity_level >= 1:    print "done!"

        string_glob_jerk_files = "%s/*ACCEL_%d_JERK_%d" % (string_ACCEL_files_dir, jerksearch_zmax, jerksearch_wmax)
        if verbosity_level >= 3:
                print "JERK: Also reading files '%s'.." % (string_glob_jerk_files)
                print "Found: ", glob.glob(string_glob_jerk_files)
                
        list_ACCEL_files = list_ACCEL_files + glob.glob(string_glob_jerk_files)
        
        if verbosity_level >= 3:
                print
                print "ACCEL files found: ", list_ACCEL_files
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        if verbosity_level >= 1:
                print "\033[1m >> TIP:\033[0m Check sifting output with '\033[1mcat %s\033[0m'" % (log_abspath)

        list_DMs = [x.split("_ACCEL")[0].split("DM")[-1] for x in list_ACCEL_files]
        candidates = sifting.read_candidates(list_ACCEL_files, track=True)

        if verbosity_level >= 3:
                print "sift_candidates:: z = %d" % (z)
                print "sift_candidates:: %s/*ACCEL_%d" % (string_ACCEL_files_dir, z)
                print "sift_candidates:: list_ACCEL_files = %s" % (list_ACCEL_file)
                print "sift_candidates:: list_DMs = %s" % (list_DMs)
                print "sift_candidates:: candidates.cands = ", candidates.cands
                print "sift_candidates:: Original N_cands = ", len(candidates.cands)
                print "sift_candidates:: sifting.sigma_threshold = ", sifting.sigma_threshold

        sifting.short_period = period_to_search_min_s
        sifting.long_period = period_to_search_max_s
        sifting.harm_pow_cutoff = 4.0
        print
        print "Selecting candidates with periods %.4f < P < %.4f seconds..." % (period_to_search_min_s, period_to_search_max_s), ; sys.stdout.flush()
        candidates.reject_shortperiod()
        candidates.reject_longperiod()
        candidates.reject_harmpowcutoff()
        print "done!"
        

        if len(candidates.cands) >=1:
                
                if flag_remove_duplicates==1: 
                        candidates = sifting.remove_duplicate_candidates(candidates)                        
                        if verbosity_level >= 1:    print "sift_candidates:: removed duplicates. N_cands = ", len(candidates.cands)
                if flag_DM_problems==1:
                        candidates = sifting.remove_DM_problems(candidates, minimum_numDMs_where_detected, list_DMs, minimum_acceptable_DM)
                        if verbosity_level >= 1:    print "sift_candidates:: removed DM probems. N_cands = ", len(candidates.cands)
                if flag_remove_harmonics==1:
                        try:
                                candidates = sifting.remove_harmonics(candidates)
                        except:
                                pass
                        if verbosity_level >= 1:    print "sift_candidates:: removed harmonics. N_cands = ", len(candidates.cands)
        #else:
        #        print "sift_candidates:: ERROR: len(candidates.cands) < 1!!! candidates = %s" % (candidates)
        #        exit()
        

        if verbosity_level >= 1:                print "sift_candidates:: Sorting the candidates by sigma...", ; sys.stdout.flush()
        try:
                candidates.sort(sifting.cmp_sigma)              # If using PRESTO 2.1's sifting.py
        except AttributeError:
                candidates.sort(key=sifting.attrgetter('sigma'), reverse=True)  #If using PRESTO 3's sifting.py

        if verbosity_level >= 1:                print "done!"

        if verbosity_level >= 1:                print "sift_candidates:: Writing down the best candidates on file '%s'..." % (best_cands_filename), ; sys.stdout.flush()
        sifting.write_candlist(candidates, best_cands_filename)
        if verbosity_level >= 1:                print "done!"

        if verbosity_level >= 1:                print "sift_candidates:: writing down report on file '%s'..." % (log_abspath), ; sys.stdout.flush()
        candidates.write_cand_report(log_abspath)
        if verbosity_level >= 1:                print "done!"

        
        return candidates






def fold_candidate(work_dir, LOG_basename, LOG_dir, raw_datafile, dir_dedispersion, obs, seg, ck, T_obs_s, candidate, ignorechan_list, mask, other_flags_prepfold="", presto_env=os.environ['PRESTO'], verbosity_level=0, flag_LOG_append=1, what_fold="rawdata", num_simultaneous_folds=1):
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
        cand = candidate
        dir_accelfile = "%s/%s/%s/%s" % (dir_dedispersion, obs, seg, ck)
        
        cand_zmax = cand.filename.split("ACCEL_")[-1].split("_JERK")[0]

        if "JERK_" in os.path.basename(cand.filename):
                cand_wmax = cand.filename.split("JERK_")[-1]
                str_zmax_wmax = "z%s_w%s" % (cand_zmax, cand_wmax)
        else:
                str_zmax_wmax =	"z%s" % (cand_zmax)
        
        
        file_script_fold_name = "script_fold.txt"
        file_script_fold_abspath = "%s/%s" % (work_dir, file_script_fold_name)
        file_script_fold = open(file_script_fold_abspath, "a")
        
        if ignorechan_list!="":
                flag_ignorechan = "-ignorechan %s " % (ignorechan_list)
        else:
                flag_ignorechan = ""

        #Write scripts for timeseries folds
        if what_fold=="timeseries":
                file_script_timeseries = "script_fold_timeseries.txt"
                file_script_timeseries_abspath = "%s/%s" % (work_dir, file_script_timeseries)
                file_script_timeseries = open(file_script_timeseries_abspath, "a")
                full_length_timeseries_basename = obs + "_full_" + "ck00_" + "DM%.2f" % (cand.DM) + ".dat"
                birdie_directory = dir_dedispersion.replace("03_DEDISPERSION", "02_BIRDIES")
                #file_to_fold = os.path.join(dir_dedispersion, obs, seg, ck, cand.filename.split("_ACCEL")[0] + ".dat" )
                file_to_fold = os.path.join(dir_dedispersion, obs, "full", "ck00", full_length_timeseries_basename)
                
                zero_dm_filename = os.path.join(birdie_directory, obs + "_DM00.00.dat")
                if candidate.p > 0.1:
                        other_flags_prepfold += " -slow "
                if seg == "full":
                    cmd_prepfold = "prepfold %s -noxwin -fixchi -accelcand %d -accelfile %s/%s.cand -o ts_fold_%s_%s_%s_DM%.2f_%s   %s" % (other_flags_prepfold, cand.candnum, dir_accelfile, cand.filename, obs, seg, ck, cand.DM, str_zmax_wmax, file_to_fold)
                    zero_dm_cmd_prepfold = "prepfold %s -noxwin -fixchi -accelcand %d -accelfile %s/%s.cand -o ts_fold_%s_%s_%s_DM%.2f_%s_zerodm   %s" % (other_flags_prepfold, cand.candnum, dir_accelfile, cand.filename, obs, seg, ck, cand.DM, str_zmax_wmax, zero_dm_filename)
                else:
                    segment_min = np.float(seg.replace("m", ""))
                    i_chunk = int(ck.replace("ck", ""))
                    T_obs_min = T_obs_s / 60.
                    start_frac = (i_chunk * segment_min) / T_obs_min
                    end_frac   = ((i_chunk + 1) * segment_min) / T_obs_min

                    cmd_prepfold = "prepfold %s -noxwin -fixchi -start %.5f -end %.5f -accelcand %d -accelfile %s/%s.cand -o ts_fold_%s_%s_%s_DM%.2f_%s   %s" % (other_flags_prepfold, start_frac, end_frac, cand.candnum, dir_accelfile, cand.filename, obs, seg, ck, cand.DM, str_zmax_wmax, file_to_fold)
                    zero_dm_cmd_prepfold = "prepfold %s -noxwin -fixchi -start %.5f -end %.5f -accelcand %d -accelfile %s/%s.cand -o ts_fold_%s_%s_%s_DM%.2f_%s_zerodm   %s" % (other_flags_prepfold, start_frac, end_frac, cand.candnum, dir_accelfile, cand.filename, obs, seg, ck, cand.DM, str_zmax_wmax, zero_dm_filename)
                #execute_and_log(cmd_prepfold, work_dir, log_abspath, dict_env, flag_LOG_append)
                file_script_timeseries.write("%s\n" % cmd_prepfold)
                file_script_timeseries.write("%s\n" % zero_dm_cmd_prepfold)
                file_script_timeseries.close()

        elif what_fold=="rawdata":
                file_to_fold = raw_datafile
                if candidate.p > 0.1:
                        other_flags_prepfold += " -slow "
                if seg == "full":
                        cmd_prepfold = "prepfold %s -noxwin -fixchi -accelcand %d -accelfile %s/%s.cand -dm %.2f %s -mask %s -o raw_fold_%s_%s_%s_DM%.2f_%s    %s" % (other_flags_prepfold, cand.candnum, dir_accelfile, cand.filename, cand.DM, flag_ignorechan, mask, obs, seg, ck, cand.DM, str_zmax_wmax, file_to_fold)
                else:
                        segment_min = np.float(seg.replace("m", ""))
                        i_chunk = int(ck.replace("ck", ""))
                        T_obs_min = T_obs_s / 60.
                        start_frac = (i_chunk * segment_min) / T_obs_min
                        end_frac   = ((i_chunk + 1) * segment_min) / T_obs_min

                        cmd_prepfold = "prepfold %s -start %.5f -end %.5f -noxwin -fixchi -accelcand %d -accelfile %s/%s.cand -dm %.2f %s -mask %s -o raw_fold_%s_%s_%s_DM%.2f_%s    %s" % (other_flags_prepfold, start_frac, end_frac, cand.candnum, dir_accelfile, cand.filename, cand.DM, flag_ignorechan, mask, obs, seg, ck, cand.DM, str_zmax_wmax, file_to_fold)

                file_script_fold.write("%s\n" % cmd_prepfold)
                if verbosity_level >= 2:
                        print cmd_prepfold
                
        if verbosity_level >= 2:
                print "fold_candidates:: cand.filename: ",  cand.filename
                print "file_to_fold = ", file_to_fold
                print "fold_candidates:: cmd_prepfold = %s" % (cmd_prepfold)

        file_script_fold.close()
        




def make_even_number(number_int):
        if int(number_int) % 2 == 1:
                return int(number_int)-1
        elif int(number_int) % 2 == 0: 
                return int(number_int)
        else:
                print "ERROR: make_even_number:: number does not appear neither EVEN nor ODD!"
                exit()

def get_command_output(command, shell_state=False, work_dir=os.getcwd()):
        list_for_Popen = command.split()
        if shell_state==False:
                proc = subprocess.Popen(list_for_Popen, stdout=subprocess.PIPE, shell=shell_state, cwd=work_dir)
        else:
                proc = subprocess.Popen([command], stdout=subprocess.PIPE, shell=shell_state, cwd=work_dir)
        out, err = proc.communicate()
        
        return out

def get_command_output_with_pipe(command1, command2):

    list_for_Popen_cmd1 = command1.split()
    list_for_Popen_cmd2 = command2.split()

    p1 = subprocess.Popen(list_for_Popen_cmd1, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(list_for_Popen_cmd2, stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close() 

    out, err = p2.communicate()
    return out


def get_rfifind_result(file_mask, LOG_file, verbosity_level=0):
        rfifind_mask = rfifind.rfifind(file_mask)

        N_int                  = rfifind_mask.nint
        N_chan                 = rfifind_mask.nchan
        N_int_masked           = len(rfifind_mask.mask_zap_ints)
        N_chan_masked          = len(rfifind_mask.mask_zap_chans)
        fraction_int_masked    = np.float(N_int_masked/N_int)
        fraction_chan_masked   = np.float(N_chan_masked/N_chan)
        
        if verbosity_level >= 2:
                print "get_rfifind_result:: file_mask: %s" % file_mask
                print "get_rfifind_result:: LOG_file: %s" % LOG_file

        if (fraction_int_masked > 0.5) or (fraction_chan_masked > 0.5):
                return "!Mask>50%"

        
        #Check if there was a problem with the clipping in first block and get the filename with that problem. Otherwise return True.
        cmd_grep_problem_clipping = "grep -l 'problem with clipping' %s" % (LOG_file) #-l option returns the name of the file that contains the expression
        cmd_grep_inf_results = "grep -l ' inf ' %s" % (LOG_file)
        output = get_command_output(cmd_grep_problem_clipping, True).strip()
        if output != "":
                if verbosity_level >= 1:
                        print
                        print "WARNING: File '%s' contains a problem with clipping in first block!" % (LOG_file)
                return "!ProbFirstBlock"

        output = get_command_output(cmd_grep_inf_results, True).strip()
        if output != "":
                if verbosity_level >= 1:
                        print
                        print "WARNING: File '%s' contains an infinite result!" % (LOG_file) 
                return "!ProbInfResult"


        return "done"
        


        

def check_prepdata_result(LOG_file, verbosity_level=0):
        #Check if there was a problem with the clipping in first block and get the filename with that problem. Otherwise return True.
        cmd_grep_problem_clipping = "grep -l 'problem with clipping' %s" % (LOG_file) #-l option returns the name of the file that contains the expression
        cmd_grep_inf_results = "grep -l ' inf ' %s" % (LOG_file)
        output = get_command_output(cmd_grep_problem_clipping, True).strip()
        print "check_prepdata_result::output: -%s-" % (output)
        if output != "":
                if verbosity_level >= 1:
                        print "WARNING: File '%s' contains a problem with clipping in first block!" % (LOG_file)
                return False

        return True


def check_rfifind_outfiles(out_dir, basename, verbosity_level=0):
        for suffix in ["bytemask", "inf", "mask", "ps", "rfi", "stats"]:
                file_to_check = "%s/%s_rfifind.%s" % (out_dir, basename, suffix)
                if not os.path.exists(file_to_check):
                        if verbosity_level >= 1:
                                print "ERROR: file %s not found!" % (file_to_check)
                        return False
                elif os.stat(file_to_check).st_size == 0:   #If the file has size 0 bytes
                        print "ERROR: file %s has size 0!" % (file_to_check)
                        return False
        return True


def check_rednoise_outfiles(fftfile_rednoise_abspath, verbosity_level=0):
        inffile_rednoise_abspath = fftfile_rednoise_abspath.replace("_red.fft", "_red.inf")

        if os.path.exists( fftfile_rednoise_abspath ) and (os.path.getsize(fftfile_rednoise_abspath) > 0) and os.path.exists(inffile_rednoise_abspath) and (os.path.getsize(inffile_rednoise_abspath) > 0):
                return True
        else:
                return False

def check_accelsearch_result(fft_infile, zmax, verbosity_level=0):
        fft_infile_nameonly = os.path.basename(fft_infile)
        fft_infile_basename = os.path.splitext(fft_infile_nameonly)[0]
        
        if verbosity_level >= 2:
                print "check_accelsearch_result:: infile_basename: ", fft_infile_basename
                print "check_accelsearch_result:: ACCEL_filename = ", ACCEL_filename
                print "check_accelsearch_result:: ACCEL_cand_filename" , ACCEL_cand_filename
                print "check_accelsearch_result:: ACCEL_txtcand_filename = ", ACCEL_txtcand_filename

        
        ACCEL_filename                =  fft_infile.replace(".fft", "_ACCEL_%d" % (zmax))
        ACCEL_cand_filename           =  fft_infile.replace(".fft", "_ACCEL_%d.cand" % (zmax))
        ACCEL_txtcand_filename        =  fft_infile.replace(".fft", "_ACCEL_%d.txtcand" % (zmax))

        try:
                if (os.path.getsize(ACCEL_filename) > 0) and (os.path.getsize(ACCEL_cand_filename) > 0) and (os.path.getsize(ACCEL_txtcand_filename) > 0):
                        result_message = "check_accelsearch_result:: Files exist and their size is > 0! Skipping..."
                        check_result = True
                else:
                        result_message = "check_accelsearch_result:: Files exists but at least one of them has size = 0!"
                        check_result = False
        except OSError:
                result_message = "check_accelsearch_result:: OSError: It seems accelsearch has not been executed!"
                check_result = False

        if verbosity_level >= 1:
                print result_message

        return check_result


def check_jerksearch_result(fft_infile, zmax, wmax, verbosity_level=0):
        fft_infile_nameonly = os.path.basename(fft_infile)
        fft_infile_basename = os.path.splitext(fft_infile_nameonly)[0]
        
        if verbosity_level >= 1:
                print "check_jerksearch_result:: infile_basename: ", fft_infile_basename
                print "check_jerksearch_result:: ACCEL_filename = ", ACCEL_filename
                print "check_jerksearch_result:: ACCEL_cand_filename" , ACCEL_cand_filename
                print "check_jerksearch_result:: ACCEL_txtcand_filename = ", ACCEL_txtcand_filename
                print "check_jerksearch_result:: sono qui 2!"
        
        ACCEL_filename                =  fft_infile.replace(".fft", "_ACCEL_%d_JERK_%d"          % (zmax, wmax))
        ACCEL_cand_filename           =  fft_infile.replace(".fft", "_ACCEL_%d_JERK_%d.cand"     % (zmax, wmax))
        ACCEL_txtcand_filename        =  fft_infile.replace(".fft", "_ACCEL_%d_JERK_%d.txtcand"  % (zmax, wmax))

        try:
                if (os.path.getsize(ACCEL_filename) > 0) and (os.path.getsize(ACCEL_cand_filename) > 0) and (os.path.getsize(ACCEL_txtcand_filename) > 0):
                        result_message = "check_jerksearch_result:: Files exist and their size is > 0! Skipping..."
                        check_result = True
                else:
                        result_message = "check_jerksearch_result:: Files exists but at least one of them has size = 0!"
                        check_result = False
        except OSError:
                result_message = "check_jerksearch_result:: OSError: It seems jerksearch has not been executed!"
                check_result = False

        if verbosity_level >= 1:
                print result_message

        return check_result


def accelsearch(infile, work_dir, log_abspath, numharm=8, zmax=0, other_flags="", dict_env = {}, verbosity_level=0, flag_LOG_append=1):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        inffile_empty = infile.replace(".fft", "_ACCEL_%d_empty" % (zmax))


        cmd_accelsearch = "accelsearch %s -zmax %s -numharm %s %s" % (other_flags, zmax, numharm, infile)
        
        if verbosity_level >= 2:
                print
                print "BEGIN ACCELSEARCH ----------------------------------------------------------------------"

                print "accelsearch:: cmd_accelsearch: ", cmd_accelsearch
                print "accelsearch:: ENV: ", dict_env
                print "accelsearch:: check_accelsearch_result(infile, int(zmax)) :: %s" % (check_accelsearch_result(infile, int(zmax)) )
                print "accelsearch:: work_dir = %s" % (work_dir)
                print "accelsearch:: infile = %s" % (infile)


        if check_accelsearch_result(infile, int(zmax)) == False and check_accelsearch_result(inffile_empty, int(zmax)) == False:
                if verbosity_level >= 2:
                        print "accelsearch:: eseguo: %s" % (cmd_accelsearch)
                execute_and_log(cmd_accelsearch, work_dir, log_abspath, dict_env, flag_LOG_append)
        else:
                if verbosity_level >= 2:
                        print "accelsearch:: WARNING: accelsearch with zmax=%d seems to have been already executed on file %s. Skipping..." % (int(zmax), infile_nameonly)

        if verbosity_level >= 2:
                print "accelsearch:: NOW I CHECK THE RESULT OF THE EXECUTION!"

        if check_accelsearch_result(infile, int(zmax)) == False:
                if verbosity_level >= 2:
                        print "False! Then I create a _empty file!"
                file_empty = open(inffile_empty, "w")
                file_empty.write("ACCELSEARCH DID NOT PRODUCE ANY CANDIDATES!")
        else:
                if verbosity_level >= 2:
                        print "accelsearch: GOOD! CANDIDATES HAVE BEEN PRODUCED for %s!" % (infile)
                
        if verbosity_level >= 2:
                print "END ACCELSEARCH ---------------------------------------------------------------------- "


def jerksearch(infile, work_dir, log_abspath, jerksearch_ncpus, numharm=4, zmax=50, wmax=150, other_flags="", dict_env={}, verbosity_level=0, flag_LOG_append=1):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        inffile_empty = infile.replace(".fft", "_ACCEL_%d_JERK_%d_empty" % (zmax, wmax))
        #print "type(jerksearch_ncpus, zmax, wmax, numharm,) ,", type(jerksearch_ncpus), type(zmax), type(wmax), type(numharm)
        sys.stdout.flush()
        cmd_jerksearch = "accelsearch %s -ncpus %d -zmax %d -wmax %d -numharm %d %s" % (other_flags, jerksearch_ncpus, zmax, wmax, numharm, infile)
        
        if verbosity_level >= 2:
                print
                print "BEGIN JERKSEARCH ----------------------------------------------------------------------"

                print "jerksearch:: cmd_jerksearch: ", cmd_jerksearch
                print "jerksearch:: AND THIS IS THE ENV: ", dict_env
                print "jerksearch:: check_accelsearch_result(infile, int(zmax)) :: %s" % (check_accelsearch_result(infile, int(zmax)) )
                print "jerksearch:: work_dir = %s" % (work_dir)
                print "jerksearch:: infile = %s" % (infile)


        if check_jerksearch_result(infile, zmax, wmax) == False and check_jerksearch_result(inffile_empty, zmax, wmax) == False:
                if verbosity_level >= 2:
                        print "jerksearch:: executing: %s" % (cmd_jerksearch)
                execute_and_log(cmd_jerksearch, work_dir, log_abspath, dict_env, flag_LOG_append)
        else:
                if verbosity_level >= 2:
                        print "jerksearch:: WARNING: jerk search with zmax=%d and wmax=%s seems to have been already executed on file %s. Skipping..." % (int(zmax), int(wmax), infile_nameonly)

        if verbosity_level >= 2:
                print "jerksearch:: NOW I CHECK THE RESULT OF THE EXECUTION!"

        if check_jerksearch_result(infile, zmax, wmax) == False:
                if verbosity_level >= 2:
                        print "False! Then I create a _empty file!"
                file_empty = open(inffile_empty, "w")
                file_empty.write("JERK SEARCH DID NOT PRODUCE ANY CANDIDATES!")
        else:
                if verbosity_level >= 2:
                        print "jerksearch:: GOOD! CANDIDATES HAVE BEEN PRODUCED for %s!" % (infile)
                
        if verbosity_level >= 2:
                print "END JERKSEARCH ---------------------------------------------------------------------- "

                
def split_into_chunks(list_datfiles_to_split, LOG_basename,  work_dir, segment_min, i_chunk, presto_env=os.environ['PRESTO'], flag_LOG_append=1, flag_remove_datfiles_of_segments=0 ):        
        segment_length_s = segment_min * 60
        dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
        
        
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        
        
        
        for datfile_name in list_datfiles_to_split:
                inffile_name = datfile_name.replace(".dat", ".inf")
                info_datfile = infodata.infodata(inffile_name)

                t_samp_s = info_datfile.dt
                
                N_samp = info_datfile.N
                T_obs_s = t_samp_s * N_samp
                
                start_fraction = (i_chunk * segment_length_s )/T_obs_s
                numout = make_even_number(int(segment_length_s / t_samp_s))

                
                string_min =  "%dm" % int(segment_min)
                string_chunck = "ck%02d" % i_chunk
                path_old = os.path.splitext(datfile_name)[0]
                path_new = path_old.replace("full", string_min).replace("ck00", string_chunck)
                
                new_outfile_name = "%s" % (os.path.basename(path_new)) 
                
                cmd_prepdata_split = "prepdata -nobary -o %s/%s -start %.3f -numout %s %s" % (work_dir, new_outfile_name, start_fraction, numout,  datfile_name)
                
                output_datfile = "%s/%s.dat" % (work_dir, new_outfile_name)
                output_inffile = "%s/%s.dat" % (work_dir, new_outfile_name)
                output_scriptfile = "%s/%s.dat.makecmd" % (work_dir, new_outfile_name)
                
                if flag_remove_datfiles_of_segments == 1 and (not os.path.exists(output_scriptfile)):
                        with open(output_scriptfile, 'w') as f:
                                f.write("%s\n" % (cmd_prepdata_split))
                        os.chmod(output_scriptfile, 0775)
                
                if check_prepdata_outfiles(output_datfile.replace(".dat", "")) == False:
                        execute_and_log(cmd_prepdata_split, work_dir, log_abspath, dict_env, flag_LOG_append)
                else:
                        if verbosity_level >= 1:
                                print "NOTE: '%s.dat' already exists. No need to create it again." % (new_outfile_name)


def check_if_DM_trial_was_searched(dat_file, list_zmax, jerksearch_zmax, jerksearch_wmax):
        dat_file_nameonly = os.path.basename(dat_file)
        fft_file = dat_file.replace(".dat", ".fft")
	fft_file_nameonly = os.path.basename(fft_file)
        
        if not os.path.exists(dat_file) or os.path.getsize(dat_file) == 0:
                return False

        for z in list_zmax:
                ACCEL_filename          = dat_file.replace(".dat", "_ACCEL_%s" % (int(z)))
                ACCEL_filename_empty    = dat_file.replace(".dat", "_ACCEL_%s_empty" % (int(z)))
                ACCEL_cand_filename     = ACCEL_filename + ".cand"
                ACCEL_txtcand_filename  = ACCEL_filename + ".txtcand"

                #print "check_if_DM_trial_was_searched:: checking: %s, %s, %s" % (ACCEL_filename, ACCEL_cand_filename, ACCEL_txtcand_filename)
                #print "check_if_DM_trial_was_searched:: checking: %s, %s, %s" % (ACCEL_filename_empty, ACCEL_cand_filename, ACCEL_txtcand_filename)
                
                
                if (not os.path.exists(ACCEL_filename)       or os.path.getsize(ACCEL_filename)==0        ) and \
                   (not os.path.exists(ACCEL_filename_empty) or os.path.getsize(ACCEL_filename_empty)==0  ):
                        return False
                if (not os.path.exists(ACCEL_cand_filename) or os.path.getsize(ACCEL_cand_filename)==0) and \
                   (not os.path.exists(ACCEL_filename_empty) or os.path.getsize(ACCEL_filename_empty)==0  ):
                        return False
                if not os.path.exists(ACCEL_txtcand_filename):
                        return False

        if jerksearch_wmax > 0:
                ACCEL_filename          = dat_file.replace(".dat", "_ACCEL_%s_JERK_%s" % (jerksearch_zmax, jerksearch_wmax))
                ACCEL_filename_empty    = dat_file.replace(".dat", "_ACCEL_%s_JERK_%s_empty" % (jerksearch_zmax, jerksearch_wmax))
                ACCEL_cand_filename     = ACCEL_filename + ".cand"
                ACCEL_txtcand_filename  = ACCEL_filename + ".txtcand"
                #print "check_if_DM_trial_was_searched:: checking: %s, %s, %s" % (ACCEL_filename, ACCEL_cand_filename, ACCEL_txtcand_filename)
                if (not os.path.exists(ACCEL_filename)       or os.path.getsize(ACCEL_filename)==0        ) and \
                   (not os.path.exists(ACCEL_filename_empty) or os.path.getsize(ACCEL_filename_empty)==0  ):
                        return False
                if (not os.path.exists(ACCEL_cand_filename) or os.path.getsize(ACCEL_cand_filename)==0) and \
                   (not os.path.exists(ACCEL_filename_empty) or os.path.getsize(ACCEL_filename_empty)==0  ):
                        return False
                if not os.path.exists(ACCEL_txtcand_filename):
                        return False

        return True
                

def periodicity_search_FFT(work_dir, LOG_basename, zapfile, segment_label, chunk_label, list_seg_ck_indices, flag_use_cuda=0, list_cuda_ids=[0], numharm=8, list_zmax=[20], jerksearch_zmax=0, jerksearch_wmax=0, jerksearch_numharm=4, jerksearch_ncpus=1, period_to_search_min_s=0.001, period_to_search_max_s=20.0, other_flags_accelsearch="", flag_remove_fftfiles=0, flag_remove_datfiles_of_segments=0, presto_env_zmax_0=os.environ['PRESTO'], presto_env_zmax_any=os.environ['PRESTO'], verbosity_level=0, flag_LOG_append=1, dict_flag_steps= {'flag_step_dedisperse':1 , 'flag_step_realfft': 1, 'flag_step_periodicity_search': 1}):

        i_seg, N_seg, i_ck, N_ck = list_seg_ck_indices
        
        if verbosity_level >= 2:
                print "periodicity_search_FFT:: Files to search: ", "%s/*DM*.*.dat, excluding red" % (work_dir)
                print "periodicity_search_FFT:: presto_env_zmax_0 = ", presto_env_zmax_0
                print "periodicity_search_FFT:: presto_env_zmax_any = ", presto_env_zmax_any
        

        list_files_to_search = sorted([ x for x in glob.glob("%s/*DM*.*.dat" % (work_dir))])
        N_files_to_search = len(list_files_to_search)
        
        frequency_to_search_max = 1./period_to_search_min_s
        frequency_to_search_min = 1./period_to_search_max_s
        if verbosity_level >= 2:
                print "frequency_to_search_min, ", frequency_to_search_min
                print "frequency_to_search_max, ", frequency_to_search_max

                print "periodicity_search_FFT:: WARNING: -flo and -fhi CURRENTLY DISABLED"
        dict_env_zmax_0   = {'PRESTO': presto_env_zmax_0,   'PATH': "%s/bin:%s" % (presto_env_zmax_0, os.environ['PATH']),   'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env_zmax_0,   os.environ['LD_LIBRARY_PATH'])}
        dict_env_zmax_any = {'PRESTO': presto_env_zmax_any, 'PATH': "%s/bin:%s" % (presto_env_zmax_any, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env_zmax_any, os.environ['LD_LIBRARY_PATH'])}

        if verbosity_level >= 2:
                print "periodicity_search_FFT:: dict_env_zmax_0 = ", dict_env_zmax_0
                print "periodicity_search_FFT:: dict_env_zmax_any = ", dict_env_zmax_any
                print "periodicity_search_FFT:: LOG_basename = ", LOG_basename
                print "periodicity_search_FFT:: list_files_to_search = ", list_files_to_search

        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        if verbosity_level >= 1:
                print
                print "\033[1m >> TIP:\033[0m Follow periodicity search with: \033[1mtail -f %s\033[0m" % (log_abspath)

        zapfile_nameonly = os.path.basename(zapfile)
        for i in range(N_files_to_search):
                print
                if verbosity_level >= 2:
                        print "periodicity_search_FFT: inside loop with i = %d / %d" % (i, N_files_to_search-1)
                dat_file = list_files_to_search[i]
                dat_file_nameonly = os.path.basename(dat_file)
                fft_file = dat_file.replace(".dat", ".fft")
                fft_file_nameonly = os.path.basename(fft_file)

                DM_trial_was_searched = check_if_DM_trial_was_searched(dat_file, list_zmax, jerksearch_zmax, jerksearch_wmax)
                
                if dict_flag_steps['flag_step_realfft'] == 1:

                        if DM_trial_was_searched == False:
                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Doing realfft  of %s..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, dat_file_nameonly), ; sys.stdout.flush()
                                realfft(dat_file, work_dir, LOG_basename, "", presto_env_zmax_0, 0, flag_LOG_append)
                                print "done!" ; sys.stdout.flush()

                                if flag_remove_datfiles_of_segments==1 and (segment_label != "full") and os.path.exists(dat_file):
                                        if verbosity_level >= 1:
                                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Removing %s to save disk space (use \"%s\" to recreate it)..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, dat_file_nameonly, dat_file_nameonly+".makecmd"), ; sys.stdout.flush()
                                        os.remove(dat_file)
                                        if verbosity_level >= 1:
                                                print "done!"; sys.stdout.flush()

                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Doing rednoise of %s..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, dat_file_nameonly), ; sys.stdout.flush()
                                rednoise(fft_file, work_dir, LOG_basename, "", presto_env_zmax_0, verbosity_level)
                                print "done!" ; sys.stdout.flush()
                                
                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Applying zapfile '%s' to '%s'..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, zapfile_nameonly, fft_file_nameonly), ; sys.stdout.flush()
                                zapped_fft_filename, zapped_inf_filename = zapbirds(fft_file, zapfile, work_dir, LOG_basename, presto_env_zmax_0, verbosity_level)
                                zapped_fft_nameonly = os.path.basename(zapped_fft_filename)
                                print "done!" ; sys.stdout.flush()
                else:
                        print "STEP_REALFFT = 0, skipping realfft, rednoise, zapbirds..."

                #print "\033[1m >> TIP:\033[0m Follow accelsearch with '\033[1mtail -f %s\033[0m'" % (log_abspath)

                if dict_flag_steps['flag_step_periodicity_search'] == 1:
                        if DM_trial_was_searched == False:
                                for z in list_zmax:
                                        tstart_accelsearch = time.time() 
                                        print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Doing accelsearch of %s with zmax = %4d..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, zapped_fft_nameonly, z), ; sys.stdout.flush()
                                        if int(z) == 0:
                                                dict_env = copy.deepcopy(dict_env_zmax_0)
                                                if verbosity_level >= 2:
                                                        print "accelsearch:: zmax == 0 ----> dict_env = %s" % (dict_env)
                                                flag_cuda = ""
                                        else:
                                                dict_env = copy.deepcopy(dict_env_zmax_any)
                                                if flag_use_cuda == 1:
                                                        gpu_id = random.choice(list_cuda_ids)
                                                        flag_cuda = " -cuda %d " % (gpu_id) 
                                                else:
                                                        flag_cuda = ""

                                                if verbosity_level >= 2:
                                                        print "periodicity_search_FFT:: zmax == %d ----> dict_env = %s" % (int(z), dict_env)
                                                        print "periodicity_search_FFT:: Now check CUDA: list_cuda_ids = ", list_cuda_ids
                                                        print "periodicity_search_FFT:: flag_use_cuda = ", flag_use_cuda
                                                        print "periodicity_search_FFT:: flag_cuda = ", flag_cuda

                                        accelsearch_flags = other_flags_accelsearch + flag_cuda #+ " -flo %s -fhi %s" % (frequency_to_search_min, frequency_to_search_max)

                                        accelsearch(fft_file, work_dir, log_abspath, numharm=numharm, zmax=z, other_flags=accelsearch_flags, dict_env=dict_env, verbosity_level=verbosity_level, flag_LOG_append=flag_LOG_append)
                                        tend_accelsearch = time.time()
                                        time_taken_accelsearch_s = tend_accelsearch -tstart_accelsearch
                                        print "done in %.2f s!" % (time_taken_accelsearch_s) ; sys.stdout.flush()
                                        ACCEL_filename = fft_file.replace(".fft", "_ACCEL_%s" % (int(z)))


                                if jerksearch_wmax > 0:
                                        tstart_jerksearch = time.time()
                                        print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Doing jerk search of %s with zmax=%d, wmax=%d, numharm=%d..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, zapped_fft_nameonly, jerksearch_zmax, jerksearch_wmax, jerksearch_numharm), ; sys.stdout.flush()
                                        flag_cuda = ""
                                        jerksearch_flags = other_flags_accelsearch + flag_cuda
                                        jerksearch(fft_file, work_dir, log_abspath, jerksearch_ncpus=jerksearch_ncpus, numharm=jerksearch_numharm, zmax=jerksearch_zmax, wmax=jerksearch_wmax, other_flags=jerksearch_flags, dict_env=dict_env_zmax_0, verbosity_level=verbosity_level, flag_LOG_append=flag_LOG_append)
                                        tend_jerksearch = time.time()
                                        time_taken_jerksearch_s = tend_jerksearch - tstart_jerksearch
                                        print "done in %.2f s!" % (time_taken_jerksearch_s) ; sys.stdout.flush()
                                        ACCEL_filename = fft_file.repglace(".fft", "_ACCEL_%s_JERK_%s" % (jerksearch_zmax, jerksearch_wmax))
                                
                        else:
                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - File '%s' was already successfully searched. Skipping..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, dat_file_nameonly)
                
                        
                if flag_remove_fftfiles==1 and os.path.exists(fft_file):
                        if verbosity_level >= 1:
                                print "Seg '%s' %d/%d | ck %d/%d | DM %d/%d - Removing %s to save disk space..." % (segment_label, i_seg+1, N_seg, i_ck+1, N_ck, i+1, N_files_to_search, fft_file_nameonly), ; sys.stdout.flush()
                        os.remove(fft_file)
                        if verbosity_level >= 1:
                                print "done!"; sys.stdout.flush()


                        
                                



def make_birds_file(ACCEL_0_filename, birds_filename, out_dir, log_filename, width_Hz, flag_grow=1, flag_barycentre=0, sigma_birdies_threshold=4, verbosity_level=0):
        infile_nameonly = os.path.basename(ACCEL_0_filename)
        infile_basename = infile_nameonly.replace("_ACCEL_0", "")
        birds_filename = ACCEL_0_filename.replace("_ACCEL_0", ".birds")
        log_file = open(log_filename, "a")

        #Skip first three lines
        if verbosity_level >= 1:
                print "make_birds_file:: Opening the candidates: %s" % (ACCEL_0_filename)
        candidate_birdies = sifting.candlist_from_candfile(ACCEL_0_filename)
        candidate_birdies.reject_threshold(sigma_birdies_threshold)

        #Write down candidates above a certain sigma threshold        
        list_birdies = candidate_birdies.cands
        if verbosity_level >= 1:
                print "make_birds_file:: Number of birdies = %d" % (len(list_birdies))
        file_birdies = open(birds_filename, "w")
        if verbosity_level >= 1:
                print "make_birds_file:: File_birdies: %s" % (birds_filename)
        for cand in list_birdies:
                file_birdies.write("%.3f     %.20f     %d     %d     %d\n" % (cand.f, width_Hz, cand.numharm, flag_grow, flag_barycentre)  )
        file_birdies.close()
        
        return birds_filename


                
def get_Fourier_bin_width(fft_infile):
        inffile_name = fft_infile.replace(".fft", ".inf")
        inffile = infodata.infodata(inffile_name)
        Tobs_s =  inffile.dt * inffile.N
        fourier_bin_width_Hz = 1./Tobs_s
        
        return fourier_bin_width_Hz

def check_zaplist_outfiles(fft_infile, verbosity_level=0):
        birds_filename    = fft_infile.replace(".fft", ".birds")
        zaplist_filename  = fft_infile.replace(".fft", ".zaplist")
        try:
                if (os.path.getsize(birds_filename) > 0) and (os.path.getsize(zaplist_filename)>0): #checks if it exists and its
                        return True
                else:
                        return False
        except OSError:
                return False

def check_prepdata_outfiles(basename, verbosity_level=0):
        dat_filename  = basename + ".dat"
        inf_filename  = basename + ".inf"
        try:
                if (os.path.getsize(dat_filename) > 0) and (os.path.getsize(inf_filename)>0): #checks if it exists and its
                        return True
                else:
                        return False
        except OSError:
                return False


def make_zaplist(fft_infile, out_dir, LOG_dir, LOG_basename, common_birdies_filename, birds_numharm=4, other_flags_accelsearch="", presto_env=os.environ['PRESTO'], verbosity_level=0):
        fft_infile_nameonly = os.path.basename(fft_infile)
        fft_infile_basename = os.path.splitext(fft_infile_nameonly)[0]
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        #file_log = open(log_abspath, "w"); file_log.close()        
        dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}

        #accelsearch
        

        if check_zaplist_outfiles(fft_infile) == False:
                if verbosity_level >= 2:              
                        print "Doing accelsearch...", ; sys.stdout.flush()
                        print fft_infile, birds_numharm, 0, other_flags_accelsearch, presto_env, verbosity_level
                accelsearch(fft_infile, out_dir, log_abspath, birds_numharm, 0, other_flags_accelsearch, dict_env, verbosity_level)
                if verbosity_level >= 2:    print "Done accelsearch!"
                ACCEL_0_filename = fft_infile.replace(".fft", "_ACCEL_0")
                fourier_bin_width_Hz = get_Fourier_bin_width(fft_infile)
                if verbosity_level >= 2:
                        print "fourier_bin_width_Hz: ", fourier_bin_width_Hz
                        print "Doing make_birds_file"; sys.stdout.flush()

                birds_filename = ACCEL_0_filename.replace("_ACCEL_0", ".birds")
                if os.path.isfile(ACCEL_0_filename):
                        make_birds_file(ACCEL_0_filename=ACCEL_0_filename, birds_filename=birds_filename, out_dir=out_dir, log_filename=log_abspath, width_Hz=fourier_bin_width_Hz, flag_grow=1, flag_barycentre=0, sigma_birdies_threshold=4, verbosity_level=0)
                #birds_filename = make_birds_file(ACCEL_0_filename=ACCEL_0_filename, out_dir=out_dir, log_filename=log_abspath, width_Hz=fourier_bin_width_Hz, flag_grow=1, flag_barycentre=0, sigma_birdies_threshold=4, verbosity_level=0)
                if verbosity_level >= 2:
                        print "Done make_birds_file!"; sys.stdout.flush()
                
                
                file_common_birdies = open(common_birdies_filename, 'r')
                file_birds          = open(birds_filename, 'a') 
                for line in file_common_birdies:
                        file_birds.write(line)
                file_birds.close()
                
                cmd_makezaplist = "makezaplist.py %s" % (birds_filename)
                if verbosity_level >= 2:
                        print "***********************************************"; sys.stdout.flush()
                        print "Doing execute_and_log"; sys.stdout.flush()
                        print "cmd_makezaplist = ", cmd_makezaplist; sys.stdout.flush()
                execute_and_log(cmd_makezaplist, out_dir, log_abspath, dict_env, 0)
                if verbosity_level >= 2:
                        print "Done execute_and_log!"; sys.stdout.flush()
                        print "***********************************************"

        else:
                if verbosity_level >= 1:
                        print "Zaplist for %s already exists! " % (fft_infile_basename),

        zaplist_filename = fft_infile.replace(".fft", ".zaplist")
        return zaplist_filename


def rednoise(fftfile, out_dir, LOG_dir, LOG_basename, other_flags="", presto_env=os.environ['PRESTO'], verbosity_level=0):
        #print "rednoise:: Inside rednoise"
       
        fftfile_nameonly = os.path.basename(fftfile)
        fftfile_basename = os.path.splitext(fftfile_nameonly)[0]
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        

        dereddened_ffts_filename = "%s/dereddened_ffts.txt" % (out_dir)
        fftfile_rednoise_abspath = os.path.join(out_dir, "%s_red.fft" % (fftfile_basename) )
        inffile_original_abspath = os.path.join(out_dir, "%s.inf" % (fftfile_basename) )
        
        
        cmd_rednoise = "rednoise %s %s" % (other_flags, fftfile)


        if verbosity_level >= 2:
                print "rednoise:: dereddened_ffts_filename = ", dereddened_ffts_filename
                print "rednoise:: fftfile_rednoise_abspath = ", fftfile_rednoise_abspath
                print "rednoise:: cmd_rednoise = ", cmd_rednoise
                #print "%s | Running:" % (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M"); sys.stdout.flush()
                #print "%s" % (cmd_rednoise) ; sys.stdout.flush()
                print "rednoise:: opening '%s'" % (dereddened_ffts_filename)

        try:
                file_dereddened_ffts = open(dereddened_ffts_filename, 'r')
        except:
                if verbosity_level >= 2:           print "rednoise:: File '%s' does not exist. Creating it..." % (dereddened_ffts_filename), ; sys.stdout.flush()
                os.mknod(dereddened_ffts_filename)
                if verbosity_level >= 2:           print "done!" ; sys.stdout.flush()
                file_dereddened_ffts = open(dereddened_ffts_filename, 'r')

        # If the fftfile is already in the list of dereddened files...
        if "%s\n" % (fftfile) in file_dereddened_ffts.readlines():
                if verbosity_level >= 2:
                        print "rednoise:: NB: File '%s' is already in the list of dereddened files (%s)." % (fftfile, dereddened_ffts_filename)
                        # Then check is the file has size > 0...
                        print "rednoise:: Checking the size of '%s'" % (fftfile)

                if (os.path.getsize(fftfile) > 0):
                        operation="skip"
                        if verbosity_level >= 2:
                                print "rednoise:: size is > 0. Then skipping..."
                else:
                        operation="make_from_scratch"
                        if verbosity_level >= 2:
                                print "rednoise:: size is = 0. Making from scratch..."

        else:
                operation="make_from_scratch"
                if verbosity_level >= 2:
                        print "rednoise:: File '%s' IS NOT in the list of dereddened files (%s). I will make the file from scratch..." % (fftfile_basename, dereddened_ffts_filename)

                
        file_dereddened_ffts.close()

        if operation=="make_from_scratch":
                if verbosity_level >= 2:
                        print "rednoise:: making the file from scratch..."
                dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
                execute_and_log(cmd_rednoise, out_dir, log_abspath, dict_env, 0)
                if verbosity_level >= 2:
                        print "done!", ; sys.stdout.flush()
                file_dereddened_ffts = open(dereddened_ffts_filename, 'a')
                file_dereddened_ffts.write("%s\n" % (fftfile))
                file_dereddened_ffts.close()
               
                os.rename(fftfile_rednoise_abspath, fftfile_rednoise_abspath.replace("_red.", "."))

                



def realfft(infile, out_dir, LOG_dir, LOG_basename, other_flags="", presto_env=os.environ['PRESTO'], verbosity_level=0, flag_LOG_append=0):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        fftfile_abspath = os.path.join(out_dir, "%s.fft" % (infile_basename) )
        cmd_realfft = "realfft %s %s" % (other_flags, infile)
        if verbosity_level >= 2:
                print "%s | realfft:: Running:" % (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M"); sys.stdout.flush()
                print "%s" % (cmd_realfft) ; sys.stdout.flush()

        if os.path.exists( fftfile_abspath ) and (os.path.getsize(fftfile_abspath) > 0):
                if verbosity_level >= 1:
                        print
                        print "WARNING: File %s already present. Skipping realfft..." % (fftfile_abspath),
        else:
                dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
                execute_and_log(cmd_realfft, out_dir, log_abspath, dict_env, 0)
                if os.path.exists( fftfile_abspath ) and (os.stat(fftfile_abspath).st_size > 0):
                        if verbosity_level >= 2:
                                print "%s | realfft on \"%s\" completed successfully!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
                else:
                        print "WARNING (%s) | could not find all the output files from realfft on \"%s\"!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
                
        

# PREPDATA
def prepdata(infile, out_dir, LOG_dir, LOG_basename, DM, Nsamples=0, ignorechan_list="", mask="", downsample_factor=1, reference="barycentric", other_flags="", presto_env=os.environ['PRESTO'], verbosity_level=0):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        #file_log = open(log_abspath, "w"); file_log.close()        
        outfile_basename = "%s_DM%05.2f" % (infile_basename, np.float(DM))
        datfile_abspath = os.path.join(out_dir, "%s.dat" % (outfile_basename))
        inffile_abspath = os.path.join(out_dir, "%s.inf" % (outfile_basename))


        if reference=="topocentric":
                flag_nobary = "-nobary "
        elif reference=="barycentric":
                flag_nobary = ""
        else:
                print "ERROR: Invalid value for barycentering option: \"%s\"" % (reference)
                exit()

        if Nsamples >= 0:
                flag_numout = "-numout %d " % ( make_even_number(int(Nsamples/np.float(downsample_factor))) )
        else:
                flag_numout = ""

        if mask!="":
                flag_mask = "-mask %s " % (mask)
        else:
                flag_mask = ""

        if ignorechan_list!="":
                flag_ignorechan = "-ignorechan %s " % (ignorechan_list)
        else:
                flag_ignorechan = ""

                
        cmd_prepdata = "prepdata -o %s %s%s %s%s%s -dm %s -downsamp %s %s" % (outfile_basename, flag_numout, flag_ignorechan, flag_mask, flag_nobary, other_flags, str(DM), downsample_factor, infile )

        if verbosity_level >= 2:
                print "%s | Running:" % (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M"); sys.stdout.flush()
                print "%s" % (cmd_prepdata) ; sys.stdout.flush()
        


        if os.path.exists( datfile_abspath ) and os.path.exists( inffile_abspath):
                if verbosity_level >= 1:
                        print
                        print "WARNING: File '%s.dat' and '%s.inf' already present. Skipping and checking results..." % (outfile_basename, outfile_basename),
        else:
                dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}

                execute_and_log(cmd_prepdata, out_dir, log_abspath, dict_env, 0)
                if os.path.exists( datfile_abspath ) and os.path.exists( inffile_abspath):
                        if verbosity_level >= 2:
                                print "%s | prepdata on \"%s\" completed successfully!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
                else:
                        print "WARNING (%s) | could not find all the output files from prepdata on \"%s\"!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
                        



def make_rfifind_mask(infile, out_dir, LOG_dir, LOG_basename, time=2.0, freqsig=6.0, timesig=10.0, intfrac=0.3, chanfrac=0.7, time_intervals_to_zap="", chans_to_zap="", other_flags="", presto_env=os.environ['PRESTO'], verbosity_level=0):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]

        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)

        flag_zapints = ""
        flag_zapchan = ""
        if time_intervals_to_zap != "":
                flag_zapints = "-zapints %s" %  (time_intervals_to_zap)
        if chans_to_zap != "":
                flag_zapchan = "-zapchan %s" %  (chans_to_zap)

        cmd_rfifind = "rfifind %s -o %s -time %s -freqsig %s -timesig %s -intfrac %s -chanfrac %s %s %s %s" % (other_flags, infile_basename, time, freqsig, timesig, intfrac, chanfrac, flag_zapints, flag_zapchan, infile)
        if verbosity_level >= 2:
                print "%s | Running:" % (datetime.datetime.now()).strftime("%Y/%m/%d  %H:%M"); sys.stdout.flush()
                print "%s" % (cmd_rfifind) ; sys.stdout.flush()
    
        flag_files_present = check_rfifind_outfiles(out_dir, infile_basename)
        
        if flag_files_present == True:
                if verbosity_level >= 1:
                        print
                        print "WARNING: File %s_rfifind.mask already present. Skipping and checking results..." % (infile_basename),
        else:
                dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
                
                execute_and_log(cmd_rfifind, out_dir, log_abspath, dict_env, 0)
                if verbosity_level >= 1:
                        print "done!"
                        
        if check_rfifind_outfiles(out_dir, infile_basename) == True:
                if verbosity_level >= 2:
                        print "make_rfifind_mask:: %s | rfifind on \"%s\" completed successfully!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
        else:
                print "WARNING (%s) | could not find all the output files from rfifind on \"%s\"!" % (datetime.datetime.now().strftime("%Y/%m/%d  %H:%M"), infile_nameonly); sys.stdout.flush()
                raise Exception("Your STEP_RFIFIND flag is set to 0, but the rfifind files could not be found!")

        
        mask_file = "%s/%s_rfifind.mask" % (out_dir, infile_basename)
        result = get_rfifind_result(mask_file, log_abspath, verbosity_level)


def get_DD_scheme_from_DDplan_output(output_DDplan):
        list_dict_schemes = []

        output_DDplan_list_lines = output_DDplan.split("\n")
        index = output_DDplan_list_lines.index("  Low DM    High DM     dDM  DownSamp   #DMs  WorkFract")   +1

        #print
        #print "+++++++++++++++++++++++++++++++++"
        #print "type(output_DDplan):", type(output_DDplan)
        print output_DDplan
        #print output_DDplan_list_lines
        #print "+++++++++++++++++++++++++++++++++"

        flag_add_plans = 1
        while flag_add_plans == 1:
                if output_DDplan_list_lines[index] == "":
                        return list_dict_schemes
                else:
                        param = output_DDplan_list_lines[index].split()
                        low_DM      = np.float(param[0])
                        high_DM     = np.float(param[1])
                        dDM         = np.float(param[2])
                        downsamp    = int(param[3])
                        num_DMs     = int(param[4])

                        if num_DMs > 1000:
                                N_schemes = int(num_DMs / 1000.) + 1
                                
                                
                                for n in range(N_schemes-1):
                                        lowDM    = low_DM + (n    * 1000 * dDM)
                                        highDM   = lowDM + 1000 * dDM
                                        dict_scheme = {'loDM': lowDM, 'highDM': highDM, 'dDM': dDM, 'downsamp': downsamp, 'num_DMs': 1000 }
                                        list_dict_schemes.append(dict_scheme)

                                lowDM    = low_DM + (N_schemes-1)   * 1000 * dDM
                                highDM   = high_DM
                                print "high_DM = ", high_DM
                                numDMs   =  int((highDM - lowDM) / dDM)
                                print "numDMs =", numDMs
				dict_scheme = {'loDM': lowDM, 'highDM': highDM, 'dDM': dDM, 'downsamp': downsamp, 'num_DMs': numDMs }
                                list_dict_schemes.append(dict_scheme)
                                        
                        else:
                                dict_scheme = {'loDM': low_DM, 'highDM': high_DM, 'dDM': dDM, 'downsamp': downsamp, 'num_DMs': num_DMs }
                                list_dict_schemes.append(dict_scheme)

                index = index + 1
                

def check_prepsubband_result(work_dir, list_DD_schemes, verbosity_level=1):
        N_schemes = len(list_DD_schemes)
        if verbosity_level >= 2:
                print "check_prepsubband_result:: list_DD_schemes = ", list_DD_schemes
                print "check_prepsubband_result:: work_dir = ", work_dir

        for i in range(N_schemes):
                for dm in np.arange(list_DD_schemes[i]['loDM'],   list_DD_schemes[i]['highDM'] - 0.5*list_DD_schemes[i]['dDM']        , list_DD_schemes[i]['dDM']):    
                        if verbosity_level >= 2:
                                print "check_prepsubband_result:: Looking for: ", os.path.join(work_dir, "*DM%.2f.dat"%(dm) ),  os.path.join(work_dir, "*DM%.2f.inf"%(dm) ) 
                                print "check_prepsubband_result:: This is what I found: %s, %s" % (  [ x for x in glob.glob(os.path.join(work_dir, "*DM%.2f.dat"%(dm))) if not "_red" in x]  , [ x for x in glob.glob(os.path.join(work_dir, "*DM%.2f.inf"%(dm))) if not "_red" in x]    )
                        if len( [ x for x in glob.glob(os.path.join(work_dir, "*DM%.2f.dat"%(dm))) if not "_red" in x]   + [ x for x in glob.glob(os.path.join(work_dir, "*DM%.2f.inf"%(dm))) if not "_red" in x] ) != 2:
                                if verbosity_level >= 2:
                                        print "check_prepsubband_result: False"
                                return False     
        if verbosity_level >= 2:
                print "check_prepsubband_result: True"

        return True

def get_DDplan_scheme(infile, out_dir, LOG_basename, loDM, highDM, DM_coherent_dedispersion, freq_central_MHz, bw_MHz, nchan, nsubbands, t_samp_s):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
 
        if np.float(DM_coherent_dedispersion) == 0:
                # Implement subbanding calculation!
                #cmd_DDplan = "DDplan.py -o ddplan_%s -l %s -d %s -f %s -b %s -n %s -s %s -t %s" % (infile_basename, loDM, highDM, freq_central_MHz, np.fabs(bw_MHz), nchan, nsubbands, t_samp_s)
                cmd_DDplan = "DDplan.py -o ddplan_%s -l %s -d %s -f %s -b %s -n %s -t %s" % (infile_basename, loDM, highDM, freq_central_MHz, np.fabs(bw_MHz), nchan, t_samp_s)
        elif np.float(DM_coherent_dedispersion) > 0:
                # Implement subbanding calculation!
                #cmd_DDplan = "DDplan.py -o ddplan_%s -l %s -d %s -c %s -f %s -b %s -n %s -s %s -t %s" % (infile_basename, loDM, highDM, DM_coherent_dedispersion, freq_central_MHz, np.fabs(bw_MHz), nchan, nsubbands, t_samp_s)
                cmd_DDplan = "DDplan.py -o ddplan_%s -l %s -d %s -c %s -f %s -b %s -n %s -t %s" % (infile_basename, loDM, highDM, DM_coherent_dedispersion, freq_central_MHz, np.fabs(bw_MHz), nchan, t_samp_s)
                print "Coherent dedispersion enabled with DM = %.3f pc cm-3" % (np.float(DM_coherent_dedispersion))

        elif np.float(DM_coherent_dedispersion) < 0:
                print "ERROR: The DM of coherent dedispersion < 0! Exiting..."
                exit()

        print "Running:  \033[1m %s \033[0m" % (cmd_DDplan)
        output_DDplan    = get_command_output(cmd_DDplan, shell_state=False, work_dir=out_dir)

        list_DD_schemes  = get_DD_scheme_from_DDplan_output(output_DDplan)


        return list_DD_schemes




def dedisperse(infile, out_dir, LOG_basename, segment_label, chunk_label, Nsamples, ignorechan_list, mask_file, list_DD_schemes, nchan, nsubbands=0, other_flags="", presto_env=os.environ['PRESTO'], verbosity_level=0):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]
        dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        N_schemes = len(list_DD_schemes)

        string_mask = ""
        if mask_file != "":  string_mask = "-mask %s" % (mask_file)
        string_ignorechan = ""
        if ignorechan_list != "":  string_ignorechan = "-ignorechan %s" % (ignorechan_list)

        print "----------------------------------------------------------------------"
        print "prepsubband will be run %d times with the following DM ranges:" % (N_schemes)
        print
        print "%10s %10s %10s %10s %10s " % ("Low DM", "High DM", "dDM",  "DownSamp",   "#DMs")
        for i in range(N_schemes):
                print "%10s %10s %10s %10s %10s " % (list_DD_schemes[i]['loDM'], np.float(list_DD_schemes[i]['loDM']) + int(list_DD_schemes[i]['num_DMs'])*np.float(list_DD_schemes[i]['dDM']), list_DD_schemes[i]['dDM'] ,  list_DD_schemes[i]['downsamp'],  list_DD_schemes[i]['num_DMs'] )
        print; sys.stdout.flush()

        if nsubbands == 0:
                nsubbands = nchan
        elif (nchan % nsubbands != 0):
                print "ERROR: requested number of subbands is %d, which is not an integer divisor of the number of channels %d! " % (nsubbands, nchan)
                exit()

        if verbosity_level >= 1:
                print "Dedispersing with %d subbands (original number of channels: %d)" % (nsubbands, nchan)
                print
                
        if verbosity_level >= 2:
                print "dedisperse::  Checking prepsubband results..."
        if check_prepsubband_result(out_dir, list_DD_schemes, verbosity_level=1) == True:
                print
                print "dedisperse:: WARNING: all the dedispersed time series for %s are already there! Skipping." % (infile_basename)
        else:
                while check_prepsubband_result(out_dir, list_DD_schemes, verbosity_level=1) == False:
                        if verbosity_level >= 2:
                                print "check_prepsubband_result(out_dir, list_DD_schemes, verbosity_level=0) = ", check_prepsubband_result(out_dir, list_DD_schemes, verbosity_level=0)
                                print "Checking results at: %s" % (out_dir)
                        if verbosity_level >= 1:
                                print "\033[1m >> TIP:\033[0m Check prepsubband progress with '\033[1mtail -f %s\033[0m'" % (log_abspath)
                        for i in range(N_schemes):
                                #if Nsamples >= 0:
                                #        flag_numout = "-numout %d " % (make_even_number(int(Nsamples/np.float(list_DD_schemes[i]['downsamp']))))
                                #else:
                                flag_numout = ""
                                        
                                prepsubband_outfilename = "%s_%s_%s" % (infile_basename, segment_label, chunk_label)
                                cmd_prepsubband = "prepsubband %s %s -o %s %s %s -lodm %s -dmstep %s -numdms %s -downsamp %s -nsub %s %s" % (other_flags, flag_numout, prepsubband_outfilename, string_ignorechan, string_mask, list_DD_schemes[i]['loDM'], list_DD_schemes[i]['dDM'], list_DD_schemes[i]['num_DMs'], list_DD_schemes[i]['downsamp'], nsubbands, infile)
                                if verbosity_level >= 1:
                                        print "Running prepsubband with scheme %d/%d on observation '%s'..." % (i+1, N_schemes, infile), ; sys.stdout.flush()
                                
                                if verbosity_level >= 2:
                                        print "dedisperse:: %d) RUNNING: %s" % (i, cmd_prepsubband)
                                execute_and_log("which prepsubband", out_dir, log_abspath, dict_env, 1)
                                execute_and_log(cmd_prepsubband, out_dir, log_abspath, dict_env, 1)
                                if verbosity_level >= 1:
                                        print "done!"; sys.stdout.flush()
                                        print
                                        print


def check_zapbirds_outfiles2(zapped_fft_filename, verbosity_level=0):
        zapped_inf_filename = zapped_fft_filename.replace(".fft", ".inf")
        
        if ("zapped" in zapped_fft_filename) and ("zapped" in zapped_inf_filename):
                try:
                        if (os.path.getsize(zapped_fft_filename) > 0) and (os.path.getsize(zapped_inf_filename)>0): #checks if it exists and its size is > 0
                                return True
                        else:
                                return False
                except OSError:
                        return False
        else:
                return False

def check_zapbirds_outfiles(fftfile, list_zapped_ffts_abspath, verbosity_level=0):
        fftfile_nameonly = os.path.basename(fftfile)
        try:
                file_list_zapped_ffts = open(list_zapped_ffts_abspath, 'r')
                if "%s\n" % (fftfile_nameonly) in file_list_zapped_ffts.readlines():
                        if verbosity_level >= 1:
                                print "check_zapbirds_outfiles:: NB: File '%s' is already in the list of zapped files (%s)." % (fftfile_nameonly, list_zapped_ffts_abspath)
                        if (os.path.getsize(fftfile) > 0):
                                if verbosity_level >= 1:
                                        print "check_zapbirds_outfiles:: size is > 0. Returning True..."
                                return True
                        else:
                                if verbosity_level >= 1:
                                        print "rednoise:: size is = 0. Returning False..."
                                return False
                else:
                        if verbosity_level >= 1:
                                print "check_zapbirds_outfiles:: File '%s' IS NOT in the list of zapped files (%s). I will zap the file from scratch..." % (fftfile_nameonly, list_zapped_ffts_abspath)
                        return False
        except:
                if verbosity_level >= 1:
                        print "check_zapbirds_outfiles:: File '%s' does not exist. Creating it and returning False..." % (list_zapped_ffts_abspath)
                os.mknod(list_zapped_ffts_abspath)
                return False
        





def zapbirds(fft_infile, zapfile_name, work_dir, LOG_basename, presto_env, verbosity_level=0):
        fft_infile_nameonly = os.path.basename(fft_infile)
        fft_infile_basename = os.path.splitext(fft_infile_nameonly)[0]
        inffile_filename = fft_infile.replace(".fft", ".inf")
        log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
        #file_log = open(log_abspath, "w"); file_log.close()        
        dict_env = {'PRESTO': presto_env, 'PATH': "%s/bin:%s" % (presto_env, os.environ['PATH']), 'LD_LIBRARY_PATH': "%s/lib:%s" % (presto_env, os.environ['LD_LIBRARY_PATH'])}

        cmd_zapbirds = "zapbirds -zap -zapfile %s %s" % (zapfile_name, fft_infile)
        zapped_fft_filename = fft_infile.replace(".fft", "_zapped.fft")
        zapped_inf_filename = inffile_filename.replace(".inf", "_zapped.inf")
        
        list_zapped_ffts_abspath = os.path.join(work_dir, "list_zapped_ffts.txt")
        if verbosity_level >= 2:
                print "zapbirds:: list_zapped_ffts_abspath = ", list_zapped_ffts_abspath

        if check_zapbirds_outfiles(fft_infile, list_zapped_ffts_abspath, verbosity_level=0) == False:
                if verbosity_level >= 2:
                        print "Running ZAPBIRDS: %s" % (cmd_zapbirds) ; sys.stdout.flush()
                execute_and_log(cmd_zapbirds, work_dir, log_abspath, dict_env, 0)
                file_list_zapped_ffts = open(list_zapped_ffts_abspath, 'a')
                file_list_zapped_ffts.write("%s\n" % (fft_infile))
                file_list_zapped_ffts.close()

        return zapped_fft_filename, zapped_inf_filename
        

def dedisperse_rednoise_and_periodicity_search_FFT(infile, out_dir, root_workdir, LOG_basename, segment_label, chunk_label, list_seg_ck_indices, zapfile, Nsamples, ignorechan_list, mask_file, list_DD_schemes, nchan, subbands=0, other_flags_prepsubband="", presto_env_prepsubband=os.environ['PRESTO'], flag_use_cuda=0, list_cuda_ids=[0], numharm=8, list_zmax=[20], jerksearch_zmax=10, jerksearch_wmax=30, jerksearch_numharm=4, jerksearch_ncpus=1, period_to_search_min_s=0.001, period_to_search_max_s=20.0, other_flags_accelsearch="", flag_remove_fftfiles=0, flag_remove_datfiles_of_segments=0, presto_env_accelsearch_zmax_0=os.environ['PRESTO'], presto_env_accelsearch_zmax_any=os.environ['PRESTO'], verbosity_level=0, dict_flag_steps = {'flag_step_dedisperse':1 , 'flag_step_realfft': 1, 'flag_step_periodicity_search': 1}):
        infile_nameonly = os.path.basename(infile)
        infile_basename = os.path.splitext(infile_nameonly)[0]

        if verbosity_level >= 2:
                print "dedisperse_rednoise_and_periodicity_search_FFT:: launching dedisperse"; sys.stdout.flush()
                print "dedisperse_rednoise_and_periodicity_search_FFT:: list_zmax = ", list_zmax



        if dict_flag_steps['flag_step_dedisperse'] == 1:
                if segment_label == "full":
                        dedisperse(infile, out_dir, LOG_basename, segment_label, chunk_label, Nsamples, ignorechan_list, mask_file, list_DD_schemes, nchan, subbands, other_flags_prepsubband, presto_env_prepsubband, verbosity_level)
                else:

                        search_string = "%s/03_DEDISPERSION/%s/full/ck00/*.dat" % (root_workdir, infile_basename) 
                        list_datfiles_to_split = glob.glob(search_string)
                        
                        if verbosity_level >= 3:
                                print "dedisperse_rednoise_and_periodicity_search_FFT:: segment_label: '%s'" % (segment_label)
                                print "search_string = ", search_string
                                print "list_datfiles_to_split = ", list_datfiles_to_split
                                
                        segment_min = np.float(segment_label.replace("m", ""))
                        i_chunk = int(chunk_label.replace("ck", ""))
                        split_into_chunks(list_datfiles_to_split, LOG_basename, out_dir, segment_min, i_chunk, presto_env=os.environ['PRESTO'], flag_LOG_append=1, flag_remove_datfiles_of_segments=flag_remove_datfiles_of_segments)

                if verbosity_level >= 2:
                        print "dedisperse_rednoise_and_periodicity_search_FFT:: launching periodicity_search_FFT"; sys.stdout.flush()
                        print "dedisperse_rednoise_and_periodicity_search_FFT:: looking for %s/*DM*.dat" % (out_dir)
                        print "dedisperse_rednoise_and_periodicity_search_FFT:: list_cuda_ids = %s" % (list_cuda_ids)
        else:
                if verbosity_level >= 2:
                        print "dedisperse_rednoise_and_periodicity_search_FFT:: STEP_DEDISPERSE = 0, skipping prepsubband..."

        
        periodicity_search_FFT(out_dir, LOG_basename, zapfile, segment_label, chunk_label, list_seg_ck_indices, flag_use_cuda, list_cuda_ids, numharm, list_zmax, jerksearch_zmax, jerksearch_wmax, jerksearch_numharm, jerksearch_ncpus, period_to_search_min_s, period_to_search_max_s, other_flags_accelsearch, flag_remove_fftfiles, flag_remove_datfiles_of_segments, presto_env_accelsearch_zmax_0, presto_env_accelsearch_zmax_any, verbosity_level, 1, dict_flag_steps)



        

class SurveyConfiguration(object):
        def __init__(self, config_filename, verbosity_level=1):
                self.config_filename = config_filename
                self.list_datafiles = []

                
                self.list_survey_configuration_ordered_params = ['SEARCH_LABEL', 'ROOT_WORKDIR', 'DATA_TYPE', 'PRESTO', 'PRESTO_GPU', 'USE_CUDA', 'CUDA_IDS', 'DM_MIN', 'DM_MAX', 'DM_COHERENT_DEDISPERSION', 'N_SUBBANDS', 'PERIOD_TO_SEARCH_MIN', 'PERIOD_TO_SEARCH_MAX', 'LIST_SEGMENTS', 'ACCELSEARCH_LIST_ZMAX', 'ACCELSEARCH_NUMHARM', 'JERKSEARCH_ZMAX', 'JERKSEARCH_WMAX', 'JERKSEARCH_NUMHARM', 'JERKSEARCH_NCPUS', 'RFIFIND_TIME', 'RFIFIND_FREQSIG', 'RFIFIND_TIMESIG', 'RFIFIND_INTFRAC', 'RFIFIND_CHANFRAC', 'RFIFIND_CHANS_TO_ZAP', 'RFIFIND_TIME_INTERVALS_TO_ZAP', 'IGNORECHAN_LIST', 'RFIFIND_FLAGS', 'PREPDATA_FLAGS', 'PREPSUBBAND_FLAGS', 'REALFFT_FLAGS', 'REDNOISE_FLAGS', 'ACCELSEARCH_FLAGS', 'ACCELSEARCH_GPU_FLAGS', 'PREPFOLD_FLAGS', 'FLAG_REMOVE_FFTFILES', 'FLAG_REMOVE_DATFILES_OF_SEGMENTS', 'SIFTING_FLAG_REMOVE_DUPLICATES', 'SIFTING_FLAG_REMOVE_DM_PROBLEMS', 'SIFTING_FLAG_REMOVE_HARMONICS', 'SIFTING_MINIMUM_NUM_DMS', 'SIFTING_MINIMUM_DM', 'SIFTING_SIGMA_THRESHOLD', 'FLAG_FOLD_KNOWN_PULSARS', 'FLAG_FOLD_TIMESERIES', 'FLAG_FOLD_RAWDATA', 'NUM_SIMULTANEOUS_FOLDS', 'STEP_RFIFIND', 'STEP_ZAPLIST', 'STEP_DEDISPERSE', 'STEP_REALFFT', 'STEP_PERIODICITY_SEARCH', 'STEP_SIFTING', 'STEP_FOLDING']

                self.dict_survey_configuration = {}
                
                config_file = open( config_filename, "r" )

                for line in config_file:
                        if line != "\n" and (not line.startswith("#")):
                                list_line = shlex.split(line)
                                self.dict_survey_configuration[list_line[0]] = list_line[1]      #Save parameter key and value in the dictionary 
                
                for key in self.dict_survey_configuration.keys():
                        if   key == "SEARCH_LABEL":                                  self.search_label                     = self.dict_survey_configuration[key]
                        elif key == "ROOT_WORKDIR":                                  self.root_workdir                     = self.dict_survey_configuration[key]
                        elif key == "FILE_LIST_DATAFILES":                           self.list_datafiles_filename          = self.dict_survey_configuration[key]
                        elif key == "FILE_COMMON_BIRDIES":                           self.file_common_birdies              = self.dict_survey_configuration[key]
                        elif key == "DATA_TYPE":                                     self.data_type                        = self.dict_survey_configuration[key]
                        elif key == "PRESTO":                                        self.presto_env                       = self.dict_survey_configuration[key]
                        elif key == "PRESTO_GPU":                                    self.presto_gpu_env                   = self.dict_survey_configuration[key]                                
                        elif key == "DM_MIN":                                        self.dm_min                           = self.dict_survey_configuration[key]
                        elif key == "DM_MAX":                                        self.dm_max                           = self.dict_survey_configuration[key]
                        elif key == "DM_COHERENT_DEDISPERSION":                      self.dm_coherent_dedispersion         = self.dict_survey_configuration[key]
                        elif key == "N_SUBBANDS":                                    self.nsubbands                        = int(self.dict_survey_configuration[key])
                        elif key == "ZAP_ISOLATED_PULSARS_FROM_FFTS":                self.zap_isolated_pulsars_from_ffts   = int(self.dict_survey_configuration[key])
                        elif key == "ZAP_ISOLATED_PULSARS_MAX_HARM":                 self.zap_isolated_pulsars_max_harm = int(self.dict_survey_configuration[key])
                        elif key == "ACCELSEARCH_LIST_ZMAX":                         self.accelsearch_list_zmax            = [int(x) for x in self.dict_survey_configuration[key].split(",")]
                        elif key == "ACCELSEARCH_NUMHARM":                           self.accelsearch_numharm              = int(self.dict_survey_configuration[key])
                        elif key == "JERKSEARCH_ZMAX":                               self.jerksearch_zmax                  = int(self.dict_survey_configuration[key])
                        elif key == "JERKSEARCH_WMAX":                               self.jerksearch_wmax                  = int(self.dict_survey_configuration[key])
                        elif key == "JERKSEARCH_NUMHARM":                            self.jerksearch_numharm               = int(self.dict_survey_configuration[key])
                        elif key == "JERKSEARCH_NCPUS":                              self.jerksearch_ncpus                 = int(self.dict_survey_configuration[key])
                        elif key == "PERIOD_TO_SEARCH_MIN":                          self.period_to_search_min             = np.float(self.dict_survey_configuration[key])
                        elif key == "PERIOD_TO_SEARCH_MAX":                          self.period_to_search_max             = np.float(self.dict_survey_configuration[key])
                        elif key == "RFIFIND_TIME":                                  self.rfifind_time                     = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_FREQSIG":                               self.rfifind_freqsig                  = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_TIMESIG":                               self.rfifind_timesig                  = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_INTFRAC":                               self.rfifind_intfrac                  = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_CHANFRAC":                              self.rfifind_chanfrac                 = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_CHANS_TO_ZAP":                          self.rfifind_chans_to_zap             = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_TIME_INTERVALS_TO_ZAP":                 self.rfifind_time_intervals_to_zap    = self.dict_survey_configuration[key]
                        elif key == "RFIFIND_FLAGS":                                 self.rfifind_flags                    = self.dict_survey_configuration[key]
                        elif key == "IGNORECHAN_LIST":                               self.ignorechan_list                  = self.dict_survey_configuration[key]
                        elif key == "PREPDATA_FLAGS":                                self.prepdata_flags                   = self.dict_survey_configuration[key]
                        elif key == "PREPSUBBAND_FLAGS":                             self.prepsubband_flags                = self.dict_survey_configuration[key]
                        elif key == "REALFFT_FLAGS":                                 self.realfft_flags                    = self.dict_survey_configuration[key]
                        elif key == "REDNOISE_FLAGS":                                self.rednoise_flags                   = self.dict_survey_configuration[key]
                        elif key == "ACCELSEARCH_FLAGS":                             self.accelsearch_flags                = self.dict_survey_configuration[key]
                        elif key == "ACCELSEARCH_GPU_FLAGS":                         self.accelsearch_gpu_flags            = self.dict_survey_configuration[key]
                        elif key == "FLAG_REMOVE_FFTFILES":                          self.flag_remove_fftfiles             = int(self.dict_survey_configuration[key])
                        elif key == "FLAG_REMOVE_DATFILES_OF_SEGMENTS":              self.flag_remove_datfiles_of_segments = int(self.dict_survey_configuration[key])
                        elif key == "USE_CUDA":                                      self.flag_use_cuda                    = int(self.dict_survey_configuration[key])
                        elif key == "CUDA_IDS":                                      self.list_cuda_ids                    = [int(x) for x in self.dict_survey_configuration[key].split(",")]
                        elif key == "LIST_SEGMENTS":                                 self.list_segments                    = self.dict_survey_configuration[key].split(",")
                        elif key == "SIFTING_FLAG_REMOVE_DUPLICATES" :               self.sifting_flag_remove_duplicates   = int(self.dict_survey_configuration[key])
                        elif key == "SIFTING_FLAG_REMOVE_DM_PROBLEMS" :              self.sifting_flag_remove_dm_problems  = int(self.dict_survey_configuration[key])
                        elif key == "SIFTING_FLAG_REMOVE_HARMONICS" :                self.sifting_flag_remove_harmonics    = int(self.dict_survey_configuration[key])
                        elif key == "SIFTING_MINIMUM_NUM_DMS" :                      self.sifting_minimum_num_DMs          = int(self.dict_survey_configuration[key])
                        elif key == "SIFTING_MINIMUM_DM" :                           self.sifting_minimum_DM               = np.float(self.dict_survey_configuration[key])
                        elif key == "SIFTING_SIGMA_THRESHOLD" :                      self.sifting_sigma_threshold          = np.float(self.dict_survey_configuration[key])
                        elif key == "PREPFOLD_FLAGS" :                               self.prepfold_flags                   = self.dict_survey_configuration[key]
                        elif key == "NUM_SIMULTANEOUS_FOLDS":                        self.num_simultaneous_folds           = int(self.dict_survey_configuration[key])
                        elif key == "FLAG_FOLD_KNOWN_PULSARS" :                      self.flag_fold_known_pulsars          = int(self.dict_survey_configuration[key])
                        elif key == "FLAG_FOLD_TIMESERIES" :                         self.flag_fold_timeseries             = int(self.dict_survey_configuration[key])
                        elif key == "FLAG_FOLD_RAWDATA" :                            self.flag_fold_rawdata                = int(self.dict_survey_configuration[key])
                        elif key == "STEP_RFIFIND":                                  self.flag_step_rfifind                = int(self.dict_survey_configuration[key])
                        elif key == "STEP_ZAPLIST":                                  self.flag_step_zaplist                = int(self.dict_survey_configuration[key])
                        elif key == "STEP_DEDISPERSE":                               self.flag_step_dedisperse             = int(self.dict_survey_configuration[key])
                        elif key == "STEP_REALFFT":                                  self.flag_step_realfft                = int(self.dict_survey_configuration[key])
                        elif key == "STEP_PERIODICITY_SEARCH":                       self.flag_step_periodicity_search     = int(self.dict_survey_configuration[key])
                        elif key == "STEP_SIFTING":                                  self.flag_step_sifting                = int(self.dict_survey_configuration[key])
                        elif key == "STEP_FOLDING":                                  self.flag_step_folding                = int(self.dict_survey_configuration[key])


                config_file.close()

                self.log_filename               = "%s.log" % (self.search_label)
                
                
                self.list_0DM_datfiles          = []
                self.list_0DM_fftfiles          = []
                self.list_0DM_fftfiles_rednoise = []
                self.list_segments_nofull       = copy.deepcopy(self.list_segments); self.list_segments_nofull.remove("full")

                
                self.dict_chunks                = {}      # {'filename': {'20m':   [0,1,2]}}
                self.dict_search_structure      = {}
                if self.presto_gpu_env == "":
                        self.presto_gpu_env = self.presto_env

                
        def get_list_datafiles(self, list_datafiles_filename):
                list_datafiles_file = open( list_datafiles_filename, "r" )
                list_datafiles = [ line.split()[0] for line in list_datafiles_file if not line.startswith("#") ] #Skip commented line
                list_datafiles_file.close()
                print "get_list_datafiles:: list_datafiles = ", list_datafiles
                
                return list_datafiles
                        
        def print_configuration(self):
                print "*********************************************"
                print "             SURVEY CONFIGURATION:"
                print "*********************************************"
                print 
                for param in self.list_survey_configuration_ordered_params:
                        print "%-32s %s" % (param, self.dict_survey_configuration[param])
                print

def init_default(observation_filename):

        # Create known_pulsars folder
        if not os.path.exists("known_pulsars"):
                os.mkdir("known_pulsars")
        
        default_file_format = "filterbank"
        default_obs = "<observation>"
        if observation_filename != "":
                default_obs = observation_filename
                if psrfits.is_PSRFITS(observation_filename) == True:
                        default_file_format = "psrfits"
                        print "Input file '%s' seems to be PSRFITS. Setting default file format to 'psrfits'." % (observation_filename)
                else:
                        print "Input file '%s' does not seem to be PSRFITS. Setting default file format to 'filterbank'." % (observation_filename)
        else:
                print "WARNING: Input observation file not provided. Setting default file format to 'filterbank'."
        try:                presto_path = os.environ['PRESTO']
        except:             presto_path = "*** PRESTO environment variable undefined ***" 

        try:
                presto_gpu_path = os.environ['PRESTO2_ON_GPU']
                use_cuda = '1'
        except:
                try:
                        presto_gpu_path = os.environ['PRESTO_ON_GPU']
                        use_cuda = '1'
                except:
                        try:
                                presto_gpu_path = os.environ['PRESTO']
                                use_cuda = '0'
                                print "WARNING: PRESTO2_ON_GPU / PRESTO_ON_GPU environment variables undefined - GPU acceleration will not be used!" 

                        except:
                                print "ERROR: no PRESTO/PRESTO_ON_GPU environment variable seems to be defined!"
                                exit()

        dict_survey_configuration_default_values = { 'SEARCH_LABEL':                        "%s               # Label of this search project" % os.path.basename(os.getcwd()),
                                                     'ROOT_WORKDIR':                        "%s               # Path of the root working directory" % os.getcwd(),
                                                     'DATA_TYPE':                           "%-18s           # Options: filterbank, psrfits" % (default_file_format),
                                                     'PRESTO':                              "%s               # Path of the main PRESTO installation" % presto_path,                                   
                                                     'PRESTO_GPU':                          "%s               # Path of the PRESTO_ON_GPU installation (if present) " % presto_gpu_path,                               
                                                     'DM_MIN':                              "2.0              # Minimum DM to search",                                   
                                                     'DM_MAX':                              "100.0            # Maximum DM to search",                                   
                                                     'DM_COHERENT_DEDISPERSION':            "0                # DM value of possible coherent dedispersion (CDD) (0 = NO CDD)",
                                                     'N_SUBBANDS':                          "0                # Number of subbands to use (0 = use all channels)",
                                                     'ZAP_ISOLATED_PULSARS_FROM_FFTS':         "0                # Zap the known pulsars in the power spectra? (1=yes, 0=no)",                    
                                                     'ZAP_ISOLATED_PULSARS_MAX_HARM':       "8                # If zap the known pulsars in the power spectra, do it up to this harmonic ",                    
                                                     'ACCELSEARCH_LIST_ZMAX':               "0,200            # List (comma-separated) of zmax values to use with PRESTO accelsearch ",                    
                                                     'ACCELSEARCH_NUMHARM':                 "8                # Number of harmonics to use for acceleration search",
                                                     'JERKSEARCH_ZMAX':                     "0                # Zmax value to use for jerk search",
                                                     'JERKSEARCH_WMAX':                     "0                # Wmax value to use for jerk search (0 = do not do jerk search)",
                                                     'JERKSEARCH_NUMHARM':                  "4                # Number of harmonics to use for jerk search",
                                                     'JERKSEARCH_NCPUS':                    "%d               # Number of CPU cores to use for jerk search" % (multiprocessing.cpu_count()),
                                                     'PERIOD_TO_SEARCH_MIN':                "0.001            # Mimimum acceptable candidate period (s) ",                     
                                                     'PERIOD_TO_SEARCH_MAX':                "20.0             # Maximum acceptable candidate period (s) ",                     
                                                     'RFIFIND_TIME':                        "2.1            # Value for RFIFIND -time option",
                                                     'RFIFIND_FREQSIG':                     "6.0            # Value for RFIFIND -freqsig option",
                                                     'RFIFIND_TIMESIG':                     "10.0           # Value for RFIFIND -timesig option",           
                                                     'RFIFIND_INTFRAC':                     "0.05           # Value for RFIFIND -intfrac option",           
                                                     'RFIFIND_CHANFRAC':                    "0.7            # Value for RFIFIND -chanfrac option",                         
                                                     'RFIFIND_CHANS_TO_ZAP':                "\"\"             # List of channels to zap in the RFIFIND mask",                     
                                                     'RFIFIND_TIME_INTERVALS_TO_ZAP':       "\"\"             # List of time intervals to zap in the RFIFIND mask",     
                                                     'RFIFIND_FLAGS':                       "\"\"             # Any additional options to give to RFIFIND",

                                                     'IGNORECHAN_LIST':                     "\"\"             # List of channels to completey ignore from the analysis (PRESTO -ignorechan option)",
                                                     'PREPDATA_FLAGS':                      "\"\"             # Any additional options to give to PREPDATA",
                                                     'PREPSUBBAND_FLAGS':                   "\"-ncpus 4\"     # Any additional options to give to PREPSUBBAND", 
                                                     'REALFFT_FLAGS':                       "\"\"             # Any additional options to give to REALFFT",
                                                     'REDNOISE_FLAGS':                      "\"\"             # Any additional options to give to REDNOISE",           
                                                     'ACCELSEARCH_FLAGS':                   "\"\"             # Any additional options to give to ACCELSEARCH",         
                                                     'ACCELSEARCH_GPU_FLAGS':               "\"\"             # Any additional options to give to ACCELSEARCH of PRESTO_ON_GPU",
                                                     'PREPFOLD_FLAGS' :                     "\"-ncpus 4 -n 64\"     # Any additional options to give to PREPFOLD",
                                                     'FLAG_REMOVE_FFTFILES':                "1               # Remove FFT files after searching to save disk space? (1=yes, 0=no)",
                                                     'FLAG_REMOVE_DATFILES_OF_SEGMENTS':    "0               # Remove .dat files of the shorter segments after searching to save disk space? (1=yes, 0=no)",
                                                     
                                                     'USE_CUDA':                            "%s               # Use GPU-acceleration? (1=yes, 0=no)" % use_cuda,                                 
                                                     'CUDA_IDS':                            "0               # Comma-separated ids of NVIDIA GPUs to use (e.g. \"0,1,2,3\" - check with 'nvidia-smi')",      
                                                     'LIST_SEGMENTS':                       "full             # Comma-separated lengths (in minutes) of chunks to search (e.g. \"full,20,10\")",                            
                                                     'NUM_SIMULTANEOUS_FOLDS':              "%-3d             # Max number of prepfold instances to run at once" % (multiprocessing.cpu_count()/2) ,   
                                                     'SIFTING_FLAG_REMOVE_DUPLICATES' :     "1               # Remove candidate duplicates when sifting? (1=yes, 0=no)",          
                                                     'SIFTING_FLAG_REMOVE_DM_PROBLEMS' :    "1               # Remove candidates that appear in few DM values? (1=yes, 0=no)",         
                                                     'SIFTING_FLAG_REMOVE_HARMONICS' :      "1               # Remove harmoniacally related candidates? (1=yes, 0=no)",           
                                                     'SIFTING_MINIMUM_NUM_DMS' :            "3               # Minimum number of DM values at which a candidate has to appear in order to be considered 'good'",                 
                                                     'SIFTING_MINIMUM_DM' :                 "2.0             # Minimum DM value at  at which a candidate has to appear in order to be considered 'good'",                      
                                                     'SIFTING_SIGMA_THRESHOLD' :            "4.0             # Minimum acceptable significance of a candidate",                 
                                                     
                                                     'FLAG_FOLD_KNOWN_PULSARS' :            "1               # Fold candidates that are likely redetections of known pulsars? (1=yes, 0=no)",          
                                                     'FLAG_FOLD_TIMESERIES' :               "0               # Fold the candidates using the time series (super-fast, but no frequency information)? (1=yes, 0=no)",                    
                                                     'FLAG_FOLD_RAWDATA' :                  "1               # Fold the candidates using raw data file (slow, but has all the information)? (1=yes, 0=no)",

                                                     'STEP_RFIFIND':                        "1               # Run the RFIFIND step? (1=yes, 0=no)",
                                                     'STEP_ZAPLIST':                        "1               # Run the ZAPLIST step? (1=yes, 0=no)",                             
                                                     'STEP_DEDISPERSE':                     "1               # Run the DEDISPERSION step? (1=yes, 0=no)",             
                                                     'STEP_REALFFT':                        "1               # Run the REALFFT step? (1=yes, 0=no)",              
                                                     'STEP_PERIODICITY_SEARCH':             "1               # Run the PERIODICITY SEARCH step? (1=yes, 0=no)",
                                                     'STEP_SIFTING':                        "1               # Run the SIFTING step? (1=yes, 0=no)",                             
                                                     'STEP_FOLDING':                        "1               # Run the FOLDING step? (1=yes, 0=no)"
                                             }

        default_cfg_filename = "%s.cfg" % (os.path.basename(os.getcwd()))
        if os.path.exists(default_cfg_filename):
                default_cfg_filename_existing = default_cfg_filename 
                default_cfg_filename = "%s_2.cfg" % (os.path.basename(os.getcwd()))
                print "******************"
                print "WARNING: '%s' already exists! Saving the default configuration onto file '%s'" % (default_cfg_filename_existing, default_cfg_filename)
                print "******************"
                print
        with open(default_cfg_filename, "w") as f:
                f.write("%-35s %s\n" % ('SEARCH_LABEL', dict_survey_configuration_default_values['SEARCH_LABEL']))
                f.write("%-35s %s\n" % ('ROOT_WORKDIR', dict_survey_configuration_default_values['ROOT_WORKDIR']))
                f.write("%-35s %s\n" % ('DATA_TYPE', dict_survey_configuration_default_values['DATA_TYPE']))
                f.write("\n")
                f.write("# PRESTO installations and GPU acceleration\n")
                f.write("%-35s %s\n" % ('PRESTO', dict_survey_configuration_default_values['PRESTO']))
                f.write("%-35s %s\n" % ('PRESTO_GPU', dict_survey_configuration_default_values['PRESTO_GPU']))
                f.write("%-35s %s\n" % ('USE_CUDA', dict_survey_configuration_default_values['USE_CUDA']))
                f.write("%-35s %s\n" % ('CUDA_IDS', dict_survey_configuration_default_values['CUDA_IDS']))
                f.write("\n")
                f.write("# Core search parameters\n")
                f.write("%-35s %s\n" % ('DM_MIN', dict_survey_configuration_default_values['DM_MIN']))
                f.write("%-35s %s\n" % ('DM_MAX', dict_survey_configuration_default_values['DM_MAX']))
                f.write("%-35s %s\n" % ('DM_COHERENT_DEDISPERSION', dict_survey_configuration_default_values['DM_COHERENT_DEDISPERSION']))
                f.write("%-35s %s\n" % ('N_SUBBANDS', dict_survey_configuration_default_values['N_SUBBANDS']))
                f.write("\n")
                f.write("%-35s %s\n" % ('ZAP_ISOLATED_PULSARS_FROM_FFTS', dict_survey_configuration_default_values['ZAP_ISOLATED_PULSARS_FROM_FFTS']))
                f.write("%-35s %s\n" % ('ZAP_ISOLATED_PULSARS_MAX_HARM', dict_survey_configuration_default_values['ZAP_ISOLATED_PULSARS_MAX_HARM']))
                f.write("\n")
                f.write("%-35s %s\n" % ('PERIOD_TO_SEARCH_MIN', dict_survey_configuration_default_values['PERIOD_TO_SEARCH_MIN']))
                f.write("%-35s %s\n" % ('PERIOD_TO_SEARCH_MAX', dict_survey_configuration_default_values['PERIOD_TO_SEARCH_MAX']))
                f.write("\n")
                f.write("%-35s %s\n" % ('LIST_SEGMENTS', dict_survey_configuration_default_values['LIST_SEGMENTS']))
                f.write("%-35s %s\n" % ('ACCELSEARCH_LIST_ZMAX', dict_survey_configuration_default_values['ACCELSEARCH_LIST_ZMAX']))
                f.write("%-35s %s\n" % ('ACCELSEARCH_NUMHARM', dict_survey_configuration_default_values['ACCELSEARCH_NUMHARM']))
                f.write("%-35s %s\n" % ('JERKSEARCH_ZMAX', dict_survey_configuration_default_values['JERKSEARCH_ZMAX']))
                f.write("%-35s %s\n" % ('JERKSEARCH_WMAX', dict_survey_configuration_default_values['JERKSEARCH_WMAX']))
                f.write("%-35s %s\n" % ('JERKSEARCH_NUMHARM', dict_survey_configuration_default_values['JERKSEARCH_NUMHARM']))
                f.write("%-35s %s\n" % ('JERKSEARCH_NCPUS', dict_survey_configuration_default_values['JERKSEARCH_NCPUS']))
                
                f.write("\n")
                f.write("# RFIFIND parameters\n")
                f.write("%-35s %s\n" % ('RFIFIND_TIME', dict_survey_configuration_default_values['RFIFIND_TIME']))
                f.write("%-35s %s\n" % ('RFIFIND_FREQSIG', dict_survey_configuration_default_values['RFIFIND_FREQSIG']))
                f.write("%-35s %s\n" % ('RFIFIND_TIMESIG', dict_survey_configuration_default_values['RFIFIND_TIMESIG']))
                f.write("%-35s %s\n" % ('RFIFIND_INTFRAC', dict_survey_configuration_default_values['RFIFIND_INTFRAC']))
                f.write("%-35s %s\n" % ('RFIFIND_CHANFRAC', dict_survey_configuration_default_values['RFIFIND_CHANFRAC']))
                f.write("%-35s %s\n" % ('RFIFIND_CHANS_TO_ZAP', dict_survey_configuration_default_values['RFIFIND_CHANS_TO_ZAP']))
                f.write("%-35s %s\n" % ('RFIFIND_TIME_INTERVALS_TO_ZAP', dict_survey_configuration_default_values['RFIFIND_TIME_INTERVALS_TO_ZAP']))
                f.write("%-35s %s\n" % ('IGNORECHAN_LIST', dict_survey_configuration_default_values['IGNORECHAN_LIST']))
                f.write("\n")
                f.write("# Additional flags for all the PRESTO routines\n")
                f.write("%-35s %s\n" % ('RFIFIND_FLAGS', dict_survey_configuration_default_values['RFIFIND_FLAGS']))
                f.write("%-35s %s\n" % ('PREPDATA_FLAGS', dict_survey_configuration_default_values['PREPDATA_FLAGS']))
                f.write("%-35s %s\n" % ('PREPSUBBAND_FLAGS', dict_survey_configuration_default_values['PREPSUBBAND_FLAGS']))
                f.write("%-35s %s\n" % ('REALFFT_FLAGS', dict_survey_configuration_default_values['REALFFT_FLAGS']))
                f.write("%-35s %s\n" % ('REDNOISE_FLAGS', dict_survey_configuration_default_values['REDNOISE_FLAGS']))
                f.write("%-35s %s\n" % ('ACCELSEARCH_FLAGS', dict_survey_configuration_default_values['ACCELSEARCH_FLAGS']))
                f.write("%-35s %s\n" % ('ACCELSEARCH_GPU_FLAGS', dict_survey_configuration_default_values['ACCELSEARCH_GPU_FLAGS']))
                f.write("%-35s %s\n" % ('PREPFOLD_FLAGS', dict_survey_configuration_default_values['PREPFOLD_FLAGS']))
                f.write("\n")
                f.write("%-35s %s\n" % ('FLAG_REMOVE_FFTFILES', dict_survey_configuration_default_values['FLAG_REMOVE_FFTFILES']))
                f.write("%-35s %s\n" % ('FLAG_REMOVE_DATFILES_OF_SEGMENTS', dict_survey_configuration_default_values['FLAG_REMOVE_DATFILES_OF_SEGMENTS']))
                f.write("%-35s %s\n" % ('SIFTING_FLAG_REMOVE_DUPLICATES', dict_survey_configuration_default_values['SIFTING_FLAG_REMOVE_DUPLICATES']))
                f.write("%-35s %s\n" % ('SIFTING_FLAG_REMOVE_DM_PROBLEMS', dict_survey_configuration_default_values['SIFTING_FLAG_REMOVE_DM_PROBLEMS']))
                f.write("%-35s %s\n" % ('SIFTING_FLAG_REMOVE_HARMONICS', dict_survey_configuration_default_values['SIFTING_FLAG_REMOVE_HARMONICS']))
                f.write("%-35s %s\n" % ('SIFTING_MINIMUM_NUM_DMS', dict_survey_configuration_default_values['SIFTING_MINIMUM_NUM_DMS']))
                f.write("%-35s %s\n" % ('SIFTING_MINIMUM_DM', dict_survey_configuration_default_values['SIFTING_MINIMUM_DM']))
                f.write("%-35s %s\n" % ('SIFTING_SIGMA_THRESHOLD', dict_survey_configuration_default_values['SIFTING_SIGMA_THRESHOLD']))
                f.write("\n")
                f.write("%-35s %s\n" % ('FLAG_FOLD_KNOWN_PULSARS', dict_survey_configuration_default_values['FLAG_FOLD_KNOWN_PULSARS']))
                f.write("%-35s %s\n" % ('FLAG_FOLD_TIMESERIES', dict_survey_configuration_default_values['FLAG_FOLD_TIMESERIES']))
                f.write("%-35s %s\n" % ('FLAG_FOLD_RAWDATA', dict_survey_configuration_default_values['FLAG_FOLD_RAWDATA']))
                f.write("%-35s %s\n" % ('NUM_SIMULTANEOUS_FOLDS', dict_survey_configuration_default_values['NUM_SIMULTANEOUS_FOLDS']))
                f.write("\n")
                f.write("# PIPELINE STEPS TO EXECUTE (1=do, 0=skip)\n")
                f.write("%-35s %s\n" % ('STEP_RFIFIND', dict_survey_configuration_default_values['STEP_RFIFIND']))
                f.write("%-35s %s\n" % ('STEP_ZAPLIST', dict_survey_configuration_default_values['STEP_ZAPLIST']))
                f.write("%-35s %s\n" % ('STEP_DEDISPERSE', dict_survey_configuration_default_values['STEP_DEDISPERSE']))
                f.write("%-35s %s\n" % ('STEP_REALFFT', dict_survey_configuration_default_values['STEP_REALFFT']))
                f.write("%-35s %s\n" % ('STEP_PERIODICITY_SEARCH', dict_survey_configuration_default_values['STEP_PERIODICITY_SEARCH']))
                f.write("%-35s %s\n" % ('STEP_SIFTING', dict_survey_configuration_default_values['STEP_SIFTING']))
                f.write("%-35s %s\n" % ('STEP_FOLDING', dict_survey_configuration_default_values['STEP_FOLDING']))
                #f.write("%-35s %s\n" % ('', dict_survey_configuration_default_values['']))

        print
        print "Default configuration written onto '%s'." % (default_cfg_filename)

        with open("common_birdies.txt", "w") as f:
                f.write("10.00    0.003     2     1     0\n")
                f.write("30.00    0.008     2     1     0\n")
                f.write("50.00    0.08      3     1     0\n")
        print "Some common birdies written on 'common_birdies.txt'."
        print
        print "Place the parfiles of the already-known pulsars, if any, in 'known_pulsars'"
        print
        print "Now edit the config file, adjust the parameters and run the pipeline with:"
        print "%s -config %s -obs %s" % (os.path.basename(sys.argv[0]), default_cfg_filename, default_obs)
        print
        exit()


def common_start_string(sa, sb):
    """ returns the longest common substring from the beginning of sa and sb """
    def _iter():
        for a, b in zip(sa, sb):
            if a == b:
                yield a
            else:
                return

    return ''.join(_iter())

###########################################################################################################################################################
verbosity_level = 1
obsname = ""

def main():
    #SHELL ARGUMENTS
    if (len(sys.argv) == 1 or ("-h" in sys.argv) or ("-help" in sys.argv) or ("--help" in sys.argv)):
            print "USAGE: %s -config <config_file> -obs <observation_file> [{-Q | -v | -V}]" % (os.path.basename(sys.argv[0]))
            print
            print "%10s  %-32s:  %-50s" % ("-h", "", "Print help")
            print "%10s  %-32s:  %-50s %s" % ("-config", "<config_file>", "Input search configuration file", "")
            print "%10s  %-32s:  %-50s" % ("-obs", "<observation_file>" , "Data file to search")
            print "%10s  %-32s:  %-50s" % ("-Q", "", "Quiet mode - do not print anything")
            print "%10s  %-32s:  %-50s" % ("-v", "", "Verbose mode - print more useful info about the processing")
            print "%10s  %-32s:  %-50s" % ("-V", "", "Very verbose mode - print everything to debug issues")
            print "%10s  %-32s:  %-50s" % ("-version", "", "Print code version")
            print
            print "To create default configuration files: \033[1m%s -init_default [<observationfile>]\033[0m" % (os.path.basename(sys.argv[0]))
            print
            exit()
    elif (("-version" in sys.argv) or ("--version" in sys.argv)):
            print "PULSAR_MINER version: %s" % (string_version)
            exit()
    else:
            for j in range(1, len(sys.argv)):
                    if (sys.argv[j] == "-config"):
                            config_filename = sys.argv[j+1]
                    elif (sys.argv[j] == "-obs"):
                        obsname = sys.argv[j+1]
                    elif (sys.argv[j] == "-init_default"):
                            try:    observation_filename = sys.argv[j+1]
                            except: observation_filename = ""
                            init_default(observation_filename)
                    elif (sys.argv[j] == "-Q"):
                            verbosity_level = 0
                    elif (sys.argv[j] == "-v"):
                            verbosity_level = 2
                    elif (sys.argv[j] == "-V"):
                            verbosity_level = 3

                            
    if verbosity_level >= 1:
            size_logo = 64
            size_string_version = len(string_version)
            dsize = int((size_logo - size_string_version)*0.5 - 1)
            dsize_offset = size_string_version % 2
            
            print
            print "#"*size_logo
            print "#" + " "*25 + "%s" % ("PULSAR MINER") + " "*25 + "#"
            print "#" + " "*(dsize + dsize_offset) + "%s" % (string_version) + " "*dsize + "#"
            print "#"*size_logo
            print

    config                  = SurveyConfiguration(config_filename, verbosity_level)



    # If input only a list of observations...
    if obsname=="":
            config.list_datafiles             = config.get_list_datafiles(list_obs_filename)    
            config.folder_datafiles           = os.path.dirname(os.path.abspath(config.list_datafiles[0]))  # ..the location of the first file is the location of all the data

    # Else, if input only a single observation...
    elif obsname!="":
            config.list_datafiles             = [os.path.basename(x) for x in glob.glob(obsname)]
            if verbosity_level >= 3:  print "config.list_datafiles = ", config.list_datafiles
            config.folder_datafiles           = os.path.dirname(os.path.abspath(obsname))   # ...the location of the input file is the location of all the data



    # Now create the list of observations to search with their absolute paths
    config.list_datafiles_abspath     = [os.path.join(config.folder_datafiles, x) for x in config.list_datafiles]

    # And create the list of Observation objects
    config.list_Observations          = [Observation(x, config.data_type) for x in config.list_datafiles_abspath]

    # Add the common birdies file
    config.file_common_birdies = os.path.join(config.root_workdir, "common_birdies.txt")


    ################################################################################
    #   IMPORT PARFILES OF KNOWN PULSARS
    ################################################################################

    dir_known_pulsars = os.path.join(config.root_workdir, "known_pulsars")

    list_known_pulsars = []
    if os.path.exists(dir_known_pulsars):
            list_parfilenames = sorted(glob.glob("%s/*.par" % dir_known_pulsars))
            dict_freqs_to_zap = {}

            
            for k in range(len(list_parfilenames)):
                    current_pulsar = Pulsar(list_parfilenames[k])
                    list_known_pulsars.append(current_pulsar)
                    
                    if not current_pulsar.is_binary:
                            current_freq = psr_utils.calc_freq( config.list_Observations[0].Tstart_MJD, current_pulsar.PEPOCH, current_pulsar.F0, current_pulsar.F1, current_pulsar.F2   )
                            dict_freqs_to_zap[current_pulsar.psr_name] = current_freq

                    if verbosity_level >= 1:
                            print "Reading '%s' --> Added %s to the list of known pulsars (%s)" % (os.path.basename(list_parfilenames[k]), current_pulsar.psr_name, current_pulsar.pulsar_type )

            if verbosity_level >= 1:
                    if config.zap_isolated_pulsars_from_ffts == 1:
                            print
                            print
                            print "WARNING: I will zap the Fourier frequencies of the isolated pulsars (up to the %d-th harmonic), namely" % (config.zap_isolated_pulsars_max_harm)
                            print
                            for key in sorted(dict_freqs_to_zap.keys()):
                                    print "%s  -->  Barycentric frequency at the epoch of the observation: %.14f Hz" % (key, dict_freqs_to_zap[key])
                            print

    for seg in config.list_segments_nofull:
            if (np.float(seg)*60) > config.list_Observations[0].T_obs_s:
                    print "Segment %d minutes > length of obs (%d minutes)" % (np.float(seg), config.list_Observations[0].T_obs_s/60.)
                    config.list_segments_nofull.remove(seg)
                    config.list_segments.remove(seg)

            

    if verbosity_level >= 2:
            config.print_configuration()

    sifting.sigma_threshold = config.sifting_sigma_threshold

    if verbosity_level >= 2: print "Checking if root '%s' directory exists..." % (config.root_workdir),; sys.stdout.flush()
    if not os.path.exists(config.root_workdir):
            if verbosity_level >= 2: print "no. Creating it...",; sys.stdout.flush()
            os.mkdir(config.root_workdir)
            print "done!"
    else:
            if verbosity_level >= 2: print "yes."; sys.stdout.flush()

    if verbosity_level >= 2:
            print "main:: SIFTING.sigma_threshold = ", sifting.sigma_threshold
            
    LOG_dir = os.path.join(config.root_workdir, "LOG")

    if verbosity_level >= 1:
            print
            print
            print "*******************************************************************"
            print "SEARCH SCHEME:"
            print "*******************************************************************"
    for i in range(len(config.list_Observations)):
            if verbosity_level >= 1:
                    print
                    print "%s: \033[1m %s \033[0m  (%.2f s)" % ("Observation", config.list_Observations[i].file_nameonly, config.list_Observations[i].T_obs_s)
                    print
                            
            config.dict_search_structure[config.list_Observations[i].file_basename] = {}
            for s in config.list_segments:
                    if verbosity_level >= 2:
                            print "Segment = %s of %s" % (s, config.list_segments)
                    if s == "full":
                            segment_length_s      = config.list_Observations[i].T_obs_s
                            segment_length_min    = config.list_Observations[i].T_obs_s /60.
                            segment_label         = s
                    else:
                            segment_length_min  = np.float(s)
                            segment_length_s    = np.float(s) * 60
                            segment_label = "%dm" % (segment_length_min)
                    config.dict_search_structure[config.list_Observations[i].file_basename][segment_label] = {}
                    N_chunks = int(config.list_Observations[i].T_obs_s / segment_length_s)
                    

                    for ck in range(N_chunks):
                            chunk_label = "ck%02d" % (ck)
                            config.dict_search_structure[config.list_Observations[i].file_basename][segment_label][chunk_label] = {'candidates': [] }
                    print "    Segment: %8s     ---> %2d chunks (%s)" % (segment_label, N_chunks, ", ".join(sorted(config.dict_search_structure[config.list_Observations[i].file_basename][segment_label].keys())))
    if verbosity_level >= 1:
            print
            print "*******************************************************************"
            print
            print
            print
            
    if verbosity_level >= 2:                  
            print "config.dict_search_structure:"
            print config.dict_search_structure


    if verbosity_level >= 1:
            print
            print "##################################################################################################"
            print "                                           STEP 1 - RFIFIND                                       "
            print "##################################################################################################"
            print



    rfifind_masks_dir = os.path.join(config.root_workdir, "01_RFIFIND")

    if not os.path.exists(rfifind_masks_dir):         os.mkdir(rfifind_masks_dir)
    if not os.path.exists(LOG_dir):                   os.mkdir(LOG_dir)


    for i in range(len(config.list_Observations)):
            time.sleep(0.2)

            config.list_Observations[i].mask = "%s/%s_rfifind.mask" % (rfifind_masks_dir, config.list_Observations[i].file_basename)
            
            if config.flag_step_rfifind == 1:
                    LOG_basename = "01_rfifind_%s" % (config.list_Observations[i].file_nameonly)
                    log_abspath = "%s/LOG_%s.txt" % (LOG_dir, LOG_basename)
                    if verbosity_level >= 1:
                            print "\033[1m >> TIP:\033[0m Check rfifind progress with '\033[1mtail -f %s\033[0m'" % (log_abspath)
                            print
                            print "Creating rfifind mask of observation %3d/%d: '%s'..." % (i+1, len(config.list_Observations), config.list_Observations[i].file_nameonly), ; sys.stdout.flush()

            
                    make_rfifind_mask( config.list_Observations[i].file_abspath,
                                                        rfifind_masks_dir,
                                                        LOG_basename,
                                                        config.rfifind_time,
                                                        config.rfifind_freqsig,
                                                        config.rfifind_timesig,
                                                        config.rfifind_intfrac,
                                                        config.rfifind_chanfrac,
                                                        config.rfifind_time_intervals_to_zap,
                                                        config.rfifind_chans_to_zap,
                                                        config.rfifind_flags,
                                                        config.presto_env,
                                                        verbosity_level
                    )

            elif config.flag_step_rfifind == 0:
                    if verbosity_level >= 1:
                            print "STEP_RFIFIND = %s   ---> I will not create the mask, I will only look for the one already present in the 01_RFIFIND folder" % (config.flag_step_rfifind)

                    if not os.path.exists(config.list_Observations[i].mask):
                            print
                            print 
                            print "\033[1m  ERROR! File '%s' not found! \033[0m" % (config.list_Observations[i].mask)
                            print
                            print "You must create a mask for your observation, in order to run the pipeline."
                            print "Set STEP_RFIFIND = 1 in your configuration file and retry."
                            print
                            exit()
                    else:
                            print
                            print "File '%s' found! Using it as the mask." % (config.list_Observations[i].mask)
                    

            

            mask = rfifind.rfifind(config.list_Observations[i].mask)
            fraction_masked_channels = np.float(len(mask.mask_zap_chans))/mask.nchan
            if verbosity_level >= 1:
                    print
                    print "RFIFIND: Percentage of frequency channels masked: %.2f%%" % (fraction_masked_channels * 100.)
                    print 
            if fraction_masked_channels > 0.5:
                    print
                    print "************************************************************************************************"
                    print "\033[1m !!! WARNING : %.2f%% of the band was masked! That seems quite a lot! \033[0m !!!" % (fraction_masked_channels * 100.)
                    print "\033[1m !!! You may want to adjust the RFIFIND parameters in the configuration file (e.g. try to increase RFIFIND_FREQSIG) \033[0m"
                    print "************************************************************************************************"
                    time.sleep(10)
                            
            weights_file = config.list_Observations[i].mask.replace(".mask", ".weights")
            if os.path.exists(weights_file):
                    array_weights = np.loadtxt(weights_file, unpack=True, usecols=(0,1,), skiprows=1)
                    config.ignorechan_list = ",".join([ str(x) for x in np.where(array_weights[1] == 0)[0] ])
                    config.nchan_ignored = len(config.ignorechan_list.split(","))
                    if verbosity_level >= 1:
                            print
                            print
                            print "WEIGHTS file '%s' found. Using it to ignore %d channels out of %d (%.2f%%)" % (os.path.basename(weights_file), config.nchan_ignored, config.list_Observations[i].nchan, 100*config.nchan_ignored/np.float(config.list_Observations[i].nchan) )
                            print "IGNORED CHANNELS: %s" % (config.ignorechan_list)




    ##################################################################################################
    # 2) BIRDIES AND ZAPLIST
    ##################################################################################################

    if verbosity_level >= 1:
            print
            print
            print
            print "##################################################################################################"
            print "                                   STEP 2 - BIRDIES AND ZAPLIST                                   "
            print "##################################################################################################"
            print
    if verbosity_level >= 2:
            print "STEP_ZAPLIST = %s" % (config.flag_step_zaplist)


    dir_birdies = os.path.join(config.root_workdir, "02_BIRDIES")

    if config.flag_step_zaplist == 1:

            if verbosity_level >= 2:
                    print "# ====================================================================================="
                    print "# a) Create a 0-DM TOPOCENTRIC time series for each of the files, using the mask."
                    print "# ====================================================================================="
            if not os.path.exists(dir_birdies):         os.mkdir(dir_birdies)
                    
                    
            for i in range(len(config.list_Observations)):
                    time.sleep(0.1)
                    print
                    print "Running prepdata to create 0-DM and topocentric time series of \"%s\"..." % (config.list_Observations[i].file_nameonly), ; sys.stdout.flush()
                    LOG_basename = "02a_prepdata_%s" % (config.list_Observations[i].file_nameonly)
                    prepdata( config.list_Observations[i].file_abspath,
                            dir_birdies,
                            LOG_basename,
                            0,
                            config.list_Observations[i].N_samples,
                            config.ignorechan_list,
                            config.list_Observations[i].mask,
                            1,
                            "topocentric",
                            config.prepdata_flags,
                            config.presto_env,
                            verbosity_level
                    )
                    if verbosity_level >= 1:
                            print "done!"; sys.stdout.flush()
                            





            if verbosity_level >= 2:
                    print "# ==============================================="
                    print "# b) Fourier transform all the files"
                    print "# ==============================================="
                    print

            config.list_0DM_datfiles = glob.glob("%s/*%s*.dat" % (dir_birdies,config.list_Observations[i].file_basename))   # Collect the *.dat files in the 02_BIRDIES_FOLDERS
            for i in range(len(config.list_0DM_datfiles)):
                    time.sleep(0.1)
                    if verbosity_level >= 1:
                            print "Running realfft on the 0-DM topocentric timeseries '%s'..." % (os.path.basename(config.list_0DM_datfiles[i])), ; sys.stdout.flush()
            
                    LOG_basename = "02b_realfft_%s" % (os.path.basename(config.list_0DM_datfiles[i]))
                    realfft(config.list_0DM_datfiles[i],
                            dir_birdies,
                            LOG_basename,
                            config.realfft_flags,
                            config.presto_env,
                            verbosity_level,
                            flag_LOG_append=0
                    )
                    
                    if verbosity_level >= 1:
                            print "done!"; sys.stdout.flush()

                                    

            if verbosity_level >= 2:
                    print
                    print "# ==============================================="
                    print "# 02c) Remove rednoise"
                    print "# ==============================================="
                    print
            config.list_0DM_fftfiles = [x for x in glob.glob("%s/*%s*DM00.00.fft" % (dir_birdies, config.list_Observations[i].file_basename)) if not "_red" in x ]  # Collect the *.fft files in the 02_BIRDIES_FOLDERS, exclude red files

            #print "len(config.list_0DM_datfiles), len(config.list_0DM_fftfiles) = ", len(config.list_0DM_datfiles), len(config.list_0DM_fftfiles)

            for i in range(len(config.list_0DM_fftfiles)):
                    time.sleep(0.1)                        
                    print "Running rednoise on the FFT \"%s\"..." % (os.path.basename(config.list_0DM_datfiles[i])) , ; sys.stdout.flush()
                    LOG_basename = "02c_rednoise_%s" % (os.path.basename(config.list_0DM_fftfiles[i]))
                    rednoise(config.list_0DM_fftfiles[i],
                            dir_birdies,
                            LOG_basename,
                            config.rednoise_flags,
                            config.presto_env,
                            verbosity_level
                    )
                    if verbosity_level >= 1:
                            print "done!"; sys.stdout.flush()



            if verbosity_level >= 2:
                    print
                    print "# ==============================================="
                    print "# 02d) Accelsearch e zaplist"
                    print "# ==============================================="
                    print
                    
            config.list_0DM_fft_rednoise_files = glob.glob("%s/*%s*_DM00.00.fft" % (dir_birdies, config.list_Observations[i].file_basename))
            for i in range(len(config.list_0DM_fft_rednoise_files)):
                    time.sleep(0.1)
                    print "Making zaplist of 0-DM topocentric time series \"%s\"..." % (os.path.basename(config.list_0DM_datfiles[i])), ; sys.stdout.flush() 
                    LOG_basename = "02d_makezaplist_%s" % (os.path.basename(config.list_0DM_fft_rednoise_files[i]))
                    zaplist_filename = make_zaplist(config.list_0DM_fft_rednoise_files[i],
                                                        dir_birdies,
                                                        LOG_basename,
                                                        config.file_common_birdies,
                                                        2,
                                                        config.accelsearch_flags,
                                                        config.presto_env,
                                                        verbosity_level
                    )
                    if verbosity_level >= 1:
                            print "done!"; sys.stdout.flush()

                    if config.zap_isolated_pulsars_from_ffts == 1:
                            fourier_bin_size =  1./config.list_Observations[0].T_obs_s
                            zaplist_file = open(zaplist_filename, 'a')

                            zaplist_file.write("########################################\n")
                            zaplist_file.write("#              KNOWN PULSARS           #\n")
                            zaplist_file.write("########################################\n")
                            for psr in sorted(dict_freqs_to_zap.keys()):
                                    zaplist_file.write("# Pulsar %s \n" % (psr))
                                    for i_harm in range(1, config.zap_isolated_pulsars_max_harm+1):
                                            zaplist_file.write("B%21.14f   %19.17f\n" % (dict_freqs_to_zap[psr]*i_harm, fourier_bin_size*i_harm))
                            zaplist_file.close()



    dir_dedispersion = os.path.join(config.root_workdir, "03_DEDISPERSION")
    if config.flag_step_dedisperse == 1:
            if verbosity_level >= 1:
                    print
                    print
                    print "##################################################################################################"
                    print "#                 STEP 3 - DEDISPERSION, DE-REDDENING AND PERIODICITY SEARCH"
                    print "##################################################################################################"
                    print
            
            if verbosity_level >= 2:        print "3) DEDISPERSION DE-REDDENING AND PERIODICITY SEARCH: creating working directories...",; sys.stdout.flush()
            if not os.path.exists(dir_dedispersion):
                    os.mkdir(dir_dedispersion)
            if verbosity_level >= 2:
                    print "done!"
                    print "get_DDplan_scheme(config.list_Observations[i].file_abspath, = ", config.list_Observations[i].file_abspath
            LOG_basename = "03_DDplan_scheme"
            list_DDplan_scheme = get_DDplan_scheme(config.list_Observations[i].file_abspath,
                                                dir_dedispersion,
                                                LOG_basename,
                                                config.dm_min,
                                                config.dm_max,
                                                config.dm_coherent_dedispersion,
                                                config.list_Observations[i].freq_central_MHz,
                                                config.list_Observations[i].bw_MHz,
                                                config.list_Observations[i].nchan,
                                                config.nsubbands,
                                                config.list_Observations[i].t_samp_s)

            ################################################################################
            # 1) LOOP OVER EACH OBSERVATION
            # 2)      LOOP OVER THE SEGMENT
            # 3)           LOOP OVER THE CHUNK



            # 1) LOOP OVER EACH OBSERVATION
            for i in range(len(config.list_Observations)):
                    obs = config.list_Observations[i].file_basename
                    time.sleep(1.0)
                    work_dir_obs = os.path.join(dir_dedispersion, config.list_Observations[i].file_basename)
                    if verbosity_level >= 2:                print "3) DEDISPERSION, DE-REDDENING AND PERIODICITY SEARCH: Creating working directory '%s'..." % (work_dir_obs),; sys.stdout.flush()
                    if not os.path.exists(work_dir_obs):
                            os.mkdir(work_dir_obs)
                    if verbosity_level >= 2:                print "done!"; sys.stdout.flush()




            # 2) LOOP OVER EACH SEGMENT
                    if "full" in config.dict_search_structure[obs].keys():
                            list_segments = ['full'] + ["%sm" % (x) for x in sorted(config.list_segments_nofull)]
                    else:
                            list_segments =  ["%sm" % (x) for x in sorted(config.list_segments_nofull)]

                    N_seg = len(list_segments)
                    for seg, i_seg in zip(list_segments, range(N_seg)):
                            work_dir_segment = os.path.join(work_dir_obs, "%s" % seg)
                            if verbosity_level >= 1:          print "\n3) DEDISPERSION, DE-REDDENING AND PERIODICITY SEARCH: creating working directory '%s'..." % (work_dir_segment),; sys.stdout.flush()
                            if not os.path.exists(work_dir_segment):
                                    os.makedirs(work_dir_segment)
                            if verbosity_level >= 1:                print "done!"; sys.stdout.flush()

            # 3) LOOP OVER THE CHUNK
                            N_ck = len(config.dict_search_structure[obs][seg].keys())
                            for ck,i_ck in zip(sorted(config.dict_search_structure[obs][seg].keys()), range(N_ck)):
                                    if verbosity_level >= 1:
                                            print
                                            print "**************************************************************"
                                            print "SEGMENT %s of %s  -- chunk %s of %s" % (seg, sorted(config.dict_search_structure[obs].keys()), ck, sorted(config.dict_search_structure[obs][seg].keys()) )
                                            print "**************************************************************"
                                    work_dir_chunk = os.path.join(work_dir_segment, ck)
                                    if verbosity_level >= 1:        print "3) DEDISPERSION, DE-REDDENING AND PERIODICITY SEARCH: Creating working directory '%s'..." % (work_dir_chunk),; sys.stdout.flush()
                                    if not os.path.exists(work_dir_chunk):
                                            os.mkdir(work_dir_chunk)
                                    if verbosity_level >= 1:                print "done!"; sys.stdout.flush()


                            
                                    LOG_basename = "03_prepsubband_and_search_FFT_%s" % (config.list_Observations[i].file_nameonly)
                                    zapfile = "%s/%s_DM00.00.zaplist" % (dir_birdies, config.list_Observations[i].file_basename)
                    

                                            
                                    if verbosity_level >= 2:
                                            print "mask::: ", config.list_Observations[i].mask
                                            print
                                            print "**********************"
                                            print
                                            print "config.list_cuda_ids = ", config.list_cuda_ids
                                            print
                                            print "config.presto_env = ", config.presto_env
                                            print "config.presto_gpu_env = ", config.presto_gpu_env
                                            print "**********************"
                            
                                    
                                    dict_flag_steps = {'flag_step_dedisperse': config.flag_step_dedisperse , 'flag_step_realfft': config.flag_step_realfft, 'flag_step_periodicity_search': config.flag_step_periodicity_search}

                                    


                                    dedisperse_rednoise_and_periodicity_search_FFT(config.list_Observations[i].file_abspath,
                                                                    work_dir_chunk,
                                                                    config.root_workdir,
                                                                    LOG_basename,
                                                                    seg,
                                                                    ck,
                                                                    [i_seg, N_seg, i_ck, N_ck],
                                                                    zapfile,
                                                                    make_even_number(config.list_Observations[i].N_samples/1.0),
                                                                    config.ignorechan_list,
                                                                    config.list_Observations[i].mask,
                                                                    list_DDplan_scheme,
                                                                    config.list_Observations[i].nchan,
                                                                    config.nsubbands,
                                                                    config.prepsubband_flags,
                                                                    config.presto_env,
                                                                    config.flag_use_cuda,
                                                                    config.list_cuda_ids,
                                                                    config.accelsearch_numharm,
                                                                    config.accelsearch_list_zmax,
                                                                    config.jerksearch_zmax,
                                                                    config.jerksearch_wmax,
                                                                    config.jerksearch_numharm,
                                                                    config.jerksearch_ncpus,
                                                                    config.period_to_search_min, 
                                                                    config.period_to_search_max, 
                                                                    config.accelsearch_flags, 
                                                                    config.flag_remove_fftfiles,
                                                                    config.flag_remove_datfiles_of_segments,
                                                                    config.presto_env,
                                                                    config.presto_gpu_env,
                                                                    verbosity_level,
                                                                    dict_flag_steps)
                                    

            





    if config.flag_step_sifting == 1:
            print
            print "##################################################################################################"
            print "#                                  STEP 4 - CANDIDATE SIFTING "
            print "##################################################################################################"


            dir_sifting = os.path.join(config.root_workdir, "04_SIFTING")
            if verbosity_level >= 1:                    print "4) CANDIDATE SIFTING: Creating working directories...",; sys.stdout.flush()
            if not os.path.exists(dir_sifting):
                    os.mkdir(dir_sifting)
            if verbosity_level >= 1:                    print "done!"


            dict_candidate_lists = {}

            for i in range(len(config.list_Observations)):
                    obs = config.list_Observations[i].file_basename
                    
                    if verbosity_level >= 2:     print "Sifting candidates for observation %3d/%d '%s'." % (i+1, len(config.list_Observations), obs) 
                    for seg in sorted(config.dict_search_structure[obs].keys()):
                            work_dir_segment = os.path.join(dir_sifting, config.list_Observations[i].file_basename, "%s" % seg)
                            if not os.path.exists(work_dir_segment):
                                    os.makedirs(work_dir_segment)

                            for ck in sorted(config.dict_search_structure[obs][seg].keys()):
                                    work_dir_chunk = os.path.join(work_dir_segment, ck)
                                    if not os.path.exists(work_dir_chunk):
                                            os.makedirs(work_dir_chunk)
                                            
                                    LOG_basename = "04_sifting_%s_%s_%s" % (obs, seg, ck)
                                    work_dir_candidate_sifting = os.path.join(dir_sifting, obs, seg, ck)

                                    if verbosity_level >= 1:        print "4) CANDIDATE SIFTING: Creating working directory '%s'..." % (work_dir_candidate_sifting),; sys.stdout.flush()
                                    if not os.path.exists(work_dir_candidate_sifting):
                                            os.mkdir(work_dir_candidate_sifting)
                                    if verbosity_level >= 1:        print "done!"


                                    if verbosity_level >= 1:
                                            print "4) CANDIDATE SIFTING: Sifting observation %d) \"%s\" / %s / %s..." % (i+1, obs, seg, ck), ; sys.stdout.flush()



                                    config.dict_search_structure[obs][seg][ck]['candidates'] = sift_candidates( work_dir_chunk,
                                                                                                                LOG_basename,
                                                                                                                LOG_dir,
                                                                                                                dir_dedispersion,
                                                                                                                obs,
                                                                                                                seg,
                                                                                                                ck,
                                                                                                                config.accelsearch_list_zmax,
                                                                                                                config.jerksearch_zmax,
                                                                                                                config.jerksearch_wmax,
                                                                                                                config.sifting_flag_remove_duplicates,
                                                                                                                config.sifting_flag_remove_dm_problems,
                                                                                                                config.sifting_flag_remove_harmonics,
                                                                                                                config.sifting_minimum_num_DMs,
                                                                                                                config.sifting_minimum_DM,
                                                                                                                config.period_to_search_min,
                                                                                                                config.period_to_search_max
                                    ) 




            for i in range(len(config.list_Observations)):
                    candidates_summary_filename = "%s/%s_cands.summary" % (dir_sifting, config.list_Observations[i].file_basename)
                    candidates_summary_file = open(candidates_summary_filename, 'w')

                    count_candidates_to_fold_all = 0
                    candidates_summary_file.write("\n*****************************************************************")
                    candidates_summary_file.write("\nCandidates found in %s:\n\n" % (config.list_Observations[i].file_nameonly))
                    for seg in sorted(config.dict_search_structure[obs].keys()):
                            for ck in sorted(config.dict_search_structure[obs][seg].keys()):
                                    Ncands_seg_ck = len(config.dict_search_structure[obs][seg][ck]['candidates'])
                                    candidates_summary_file.write("%20s  |  %10s  ---> %4d candidates\n" % (seg, ck, Ncands_seg_ck))
                                    count_candidates_to_fold_all = count_candidates_to_fold_all + Ncands_seg_ck
                    candidates_summary_file.write("\nTOT = %d candidates\n" % (count_candidates_to_fold_all))
                    candidates_summary_file.write("*****************************************************************\n\n")


                    count_candidates_to_fold_redet = 0
                    count_candidates_to_fold_new = 0
                    list_all_cands = []
                    for seg in sorted(config.dict_search_structure[obs].keys()):
                            for ck in sorted(config.dict_search_structure[obs][seg].keys()):
                                    config.dict_search_structure[obs][seg][ck]['candidates_redetections'] = []
                                    config.dict_search_structure[obs][seg][ck]['candidates_new'] = []
                    
                                    for j in range(len(config.dict_search_structure[obs][seg][ck]['candidates'])):
                                            candidate = config.dict_search_structure[obs][seg][ck]['candidates'][j]

                                            flag_is_know, known_psrname, str_harmonic = check_if_cand_is_known(candidate, list_known_pulsars, numharm=16)

                                            
                                            if flag_is_know == True:
                                                    config.dict_search_structure[obs][seg][ck]['candidates_redetections'].append(candidate)
                                                    count_candidates_to_fold_redet = count_candidates_to_fold_redet +1
                                            elif flag_is_know == False:
                                                    config.dict_search_structure[obs][seg][ck]['candidates_new'].append(candidate)
                                                    count_candidates_to_fold_new = count_candidates_to_fold_new + 1
                                                    
                                            dict_cand = {'cand': candidate, 'obs': obs, 'seg': seg, 'ck': ck, 'is_known': flag_is_know, 'known_psrname': known_psrname, 'str_harmonic': str_harmonic }
                                            list_all_cands.append(dict_cand)
                    N_cands_all = len(list_all_cands)
                    
                    for i_cand, dict_cand in zip(range(0, N_cands_all), sorted(list_all_cands, key=lambda k: k['cand'].p, reverse=False)):
                            if dict_cand['cand'].DM < 2:
                                    candidates_summary_file.write("Cand %4d/%d: %12.6f ms    |  DM: %7.2f pc cm-3    (%4s / %4s)  ---> Likely RFI\n" % (i_cand+1, N_cands_all, dict_cand['cand'].p * 1000., dict_cand['cand'].DM, dict_cand['seg'], dict_cand['ck'] ))
                            else:
                                    if dict_cand['is_known'] == True:
                                            candidates_summary_file.write("Cand %4d/%d:  %12.6f ms  |  DM: %7.2f pc cm-3    (%4s / %4s)  ---> Likely %s - %s\n" % (i_cand+1, N_cands_all, dict_cand['cand'].p * 1000., dict_cand['cand'].DM, dict_cand['seg'], dict_cand['ck'], dict_cand['known_psrname'], dict_cand['str_harmonic']))
                                    elif dict_cand['is_known'] == False:
                                            candidates_summary_file.write("Cand %4d/%d:  %12.6f ms  |  DM: %7.2f pc cm-3    (%4s / %4s)\n" % (i_cand+1, N_cands_all, dict_cand['cand'].p * 1000., dict_cand['cand'].DM, dict_cand['seg'], dict_cand['ck']))

                    
                    candidates_summary_file.close()
                    
                    if verbosity_level >= 1:
                            candidates_summary_file = open(candidates_summary_filename, 'r')
                            for line in candidates_summary_file:
                                    print line,
                            candidates_summary_file.close()



            
                                    

    if config.flag_step_folding == 1:
            print
            print
            print "##################################################################################################"
            print "#                                       STEP 5 - FOLDING "
            print "##################################################################################################"
            print

            dir_folding = os.path.join(config.root_workdir, "05_FOLDING")
            if verbosity_level >= 1: print "5) FOLDING: Creating working directories...",; sys.stdout.flush()
            if not os.path.exists(dir_folding):
                    os.mkdir(dir_folding)
            if verbosity_level >= 1: print "done!"

            for i in range(len(config.list_Observations)):
                    obs = config.list_Observations[i].file_basename
                    print "Folding observation '%s'" % (obs)
                    print

                    work_dir_candidate_folding = os.path.join(dir_folding, config.list_Observations[i].file_basename)
                    if verbosity_level >= 1:   print "5) CANDIDATE FOLDING: creating working directory '%s'..." % (work_dir_candidate_folding),; sys.stdout.flush()
                    if not os.path.exists(work_dir_candidate_folding):
                            os.mkdir(work_dir_candidate_folding)
                    if verbosity_level >= 1:   print "done!"
                    

                    file_script_fold_name = "script_fold.txt"
                    file_script_fold_abspath = "%s/%s" % (work_dir_candidate_folding, file_script_fold_name)
                    file_script_fold = open(file_script_fold_abspath, "w")
                    file_script_fold.close()

                    if config.flag_fold_known_pulsars == 1:
                            key_cands_to_fold = 'candidates'
                            if verbosity_level >= 1:
                                    print
                                    print "5) CANDIDATE FOLDING: I will fold all the %d candidates (%s likely redetections included)" % (N_cands_all, count_candidates_to_fold_redet)
                            N_cands_to_fold = N_cands_all
                            
                    elif config.flag_fold_known_pulsars == 0:
                            key_cands_to_fold = 'candidates_new'
                            if verbosity_level >= 1:
                                    print
                                    print "5) CANDIDATE FOLDING: I will fold only the %d putative new pulsars (%s likely redetections will not be folded)" % (count_candidates_to_fold_new, count_candidates_to_fold_redet)
                            N_cands_to_fold = count_candidates_to_fold_new
                    count_folded_ts = 1 
                    if config.flag_fold_timeseries == 1:
                            
                            LOG_basename = "05_folding_%s_timeseries" % (obs)
                            if verbosity_level >= 1:
                                    print
                                    print "Folding time series..."
                                    print 
                                    print "\033[1m >> TIP:\033[0m Follow folding progress with '\033[1mtail -f %s/LOG_%s.txt\033[0m'" % (LOG_dir, LOG_basename)
                                    print
                            for seg in sorted(config.dict_search_structure[obs].keys()):
                                    for ck in sorted(config.dict_search_structure[obs][seg].keys()):
                                            for j in range(len(config.dict_search_structure[obs][seg][ck][key_cands_to_fold])):
                                                    candidate = config.dict_search_structure[obs][seg][ck][key_cands_to_fold][j]
                                            
                                                    print "FOLDING CANDIDATE TIMESERIES %d/%d of %s: seg %s / %s..." % (count_folded_ts, N_cands_to_fold, obs, seg, ck), ; sys.stdout.flush()
                                                    tstart_folding_cand_ts = time.time()
                                                    file_to_fold = os.path.join(dir_dedispersion, obs, seg, ck, candidate.filename.split("_ACCEL")[0] + ".dat" )
                                                    flag_remove_dat_after_folding = 0
                                                    if os.path.exists(file_to_fold):
                                                            
                                                            fold_candidate(work_dir_candidate_folding,  
                                                                                        LOG_basename, 
                                                                                        config.list_Observations[i].file_abspath,
                                                                                        dir_dedispersion,
                                                                                        obs,
                                                                                        seg,
                                                                                        ck,
                                                                                        config.list_Observations[i].T_obs_s,
                                                                                        candidate,
                                                                                        config.ignorechan_list,
                                                                                        config.list_Observations[i].mask,
                                                                                        config.prepfold_flags,
                                                                                        config.presto_env,
                                                                                        verbosity_level,
                                                                                        1,
                                                                                        "timeseries",
                                                                                        config.num_simultaneous_folds
                                                            )
                                                            tend_folding_cand_ts = time.time()
                                                            time_taken_folding_cand_ts_s = tend_folding_cand_ts - tstart_folding_cand_ts
                                                            print "done in %.2f s!" % (time_taken_folding_cand_ts_s) ; sys.stdout.flush()
                                                            count_folded_ts = count_folded_ts + 1
                                                    else:
                                                            print "dat file does not exists! Likely if you set FLAG_REMOVE_DATFILES_OF_SEGMENTS = 1 in the config file. Skipping..."
                                            
                    count_folded_raw = 1 
                    if config.flag_fold_rawdata == 1:
                            LOG_basename = "05_folding_%s_rawdata" % (obs)
                            print
                            print "Folding raw data \033[1m >> TIP:\033[0m Follow folding progress with '\033[1mtail -f %s/LOG_%s.txt\033[0m'" % (LOG_dir,LOG_basename)
                            for seg in sorted(config.dict_search_structure[obs].keys(), reverse=True):
                                    #print "FOLD_RAW = %s of %s" % (seg, sorted(config.dict_search_structure[obs].keys(), reverse=True))
                                    
                                    for ck in sorted(config.dict_search_structure[obs][seg].keys()):
                                            for j in range(len(config.dict_search_structure[obs][seg][ck][key_cands_to_fold])):
                                                    candidate = config.dict_search_structure[obs][seg][ck][key_cands_to_fold][j]
                                                    LOG_basename = "05_folding_%s_%s_%s_rawdata" % (obs, seg, ck)
                                                    

                                                    #print "FOLDING CANDIDATE RAW %d/%d of %s: seg %s / %s ..." % (count_folded_raw, count_candidates_to_fold, obs, seg, ck), ; sys.stdout.flush()
                                                    fold_candidate(work_dir_candidate_folding,  
                                                                                        LOG_basename, 
                                                                                        config.list_Observations[i].file_abspath,
                                                                                        dir_dedispersion,
                                                                                        obs,
                                                                                        seg,
                                                                                        ck,
                                                                                        config.list_Observations[i].T_obs_s,
                                                                                        candidate,
                                                                                        config.ignorechan_list,
                                                                                        config.list_Observations[i].mask,
                                                                                        config.prepfold_flags + " -nsub %d" % (config.list_Observations[i].nchan),
                                                                                        config.presto_env,
                                                                                        verbosity_level,
                                                                                        1,
                                                                                        "rawdata",
                                                                                        config.num_simultaneous_folds
                                                    )
                                                    
                                                    #print "done!"

                                                    count_folded_raw = count_folded_raw + 1


                    os.chdir(work_dir_candidate_folding)
                    cmd_pm_run_multithread = "%s/pm_run_multithread -cmdfile %s -ncpus %d" % (os.path.dirname(sys.argv[0]), file_script_fold_abspath, config.num_simultaneous_folds)
                    print
                    print 
                    print "5) CANDIDATE FOLDING - Now running:"
                    print "%s" % cmd_pm_run_multithread
                    os.system(cmd_pm_run_multithread)
                    
if __name__ == "__main__":
        main()