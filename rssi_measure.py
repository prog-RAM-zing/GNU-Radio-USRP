#!/usr/bin/env python
#
# Copyright 2005,2007 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.


#----- imports from python and gnuradio libraries -----#
from gnuradio import gr, eng_notation
from gnuradio import blocks
from gnuradio import audio
from gnuradio import filter
from gnuradio import fft
from gnuradio import uhd
from gnuradio.eng_option import eng_option
from optparse import OptionParser
from time import sleep
import subprocess,shlex
import pickle
import scipy
import math, os,re, getpass


from gnuradio import digital
from receive_path import receive_path
import threading,Queue
from uhd_interface import uhd_receiver
from scipy import special

import sqlite3
import datetime
import struct,socket
import sys

#----- Top block of Power Estimator -----#
class powerestimator(gr.top_block):

    def __init__(self,demodulator, rx_callback, options):

        gr.top_block.__init__(self)
        '''
        Constructor for top block of Power Estimator
        Creates the graph for calculating mean and variance
        '''

        if(options.rx_freq is not None):
            # Work-around to get the modulation's bits_per_symbol
            args = demodulator.extract_kwargs_from_options(options)
            symbol_rate = options.bitrate / demodulator(**args).bits_per_symbol()
        ########## Node 1 - USRP Source ##########
            self.u= uhd_receiver(options.args, symbol_rate,
                                       options.samples_per_symbol, options.rx_freq,
                                       options.lo_offset, options.rx_gain,
                                       options.spec, options.antenna,
                                       options.clock_source, options.verbose)
            #options.samples_per_symbol = self.source._sps


            self.rxpath = receive_path(demodulator, rx_callback, options)
        if options.type == 'Rx' or options.type=='Rx/S':
            self.connect(self.u, self.rxpath)

        ########## Node 2 - Data Statistic Generator ##########

        self.d = periodogram(options)

        ########## Connect - USRP to DS Generator ##########
        if options.type=='Rx/S' or options.type=='S':
            self.connect(self.u,self.d)

#----- Data Statistic Generator -----#
class periodogram(gr.hier_block2):

    def __init__(self,options):
        '''
            Constructor for top block of Power Estimator
            Creates the graph for calculating mean and variance
        '''
        gr.hier_block2.__init__(self, "periodogram", \
                                    gr.io_signature(1,1,gr.sizeof_gr_complex), \
                                    gr.io_signature(0,0,0) )

        scalarx=blocks.multiply_const_cc(1)

        ########## Node 1 - streams2vector block (input from usrp & output to fft block) ##########
        s2v = blocks.stream_to_vector(gr.sizeof_gr_complex, options.fft_size)

        #Node 3 - fft block
        mywindow = filter.window.blackmanharris(options.fft_size)
        ffter = fft.fft_vcc(options.fft_size, True, mywindow)

        #Node 4 - magnitude-squared block
        c2mag = blocks.complex_to_mag_squared(options.fft_size)

        #Node 5 - vector2stream block
        vector2stream = blocks.vector_to_stream(gr.sizeof_float,options.fft_size)

        #Node 6 - stream2streams block
        stream2streams = blocks.stream_to_streams(gr.sizeof_float, options.fft_size)

        #Node 7 - adder block
        self.sumofNstreams = blocks.add_ff()

        #Node 8 - multiplier block (used to divide the output of adder block)
        self.avgofNstreams = blocks.multiply_const_ff(1.0/options.noofbins) # TODO: will depend on the number of bins

        #Node 9 - sinks (vector and null)
        to_nullsink = blocks.streams_to_stream(gr.sizeof_float,10)
        #self.vsink = gr.vector_sink_f()
        self.fsink = blocks.file_sink(gr.sizeof_float,"fsink.dat")
        if options.fft_size != options.noofbins:
            streams2stream = blocks.streams_to_stream(gr.sizeof_float, options.fft_size-options.noofbins)
        nullsink = blocks.null_sink(gr.sizeof_float)

        #Connect Phase 1 - From USRP source to stream2streams
        self.connect(self, scalarx, s2v, ffter, c2mag, vector2stream,stream2streams)
        for index in range(options.noofbins):
            self.connect((stream2streams,index), (self.sumofNstreams, index))
        i=10
        #Connect Phase 2 - From stream2streams to adder(few) and streams2stream(remaining)
        '''for index in range(5):
            self.connect((stream2streams,index), (to_nullsink,index))
        for index in range(5,options.noofbins-5):
            self.connect((stream2streams,index), (sumofNstreams, index-5))
        for index in range(options.fft_size-5,options.fft_size):
            self.connect((stream2streams,index), (to_nullsink,i))
            i=i+1
        else:
            for index in range(5,options.noofbins+5):
                self.connect((stream2streams,index), (sumofNstreams, index-5))
            for index in range(options.noofbins+5,options.fft_size):
                self.connect((stream2streams,index), (streams2stream,index-options.noofbins))'''

        #Connect Phase 3 - (few) from adder to vector sink, (remaining) to null sink
        #self.connect(streams2stream, nullsink)
        self.connect(self.sumofNstreams,self.avgofNstreams,self.fsink)

        #self.connect(to_nullsink,nullsink)

        print "FFT size                 %d" % (options.fft_size)
        print "Nblocks considered       %d" % (options.nblocks)
        print "No.of bins considered    %d" % (options.noofbins)

    def get_data(self):
        '''
            Returns the contents of the Vector Sink
        '''
        t = gr.top_block()
        fsource = blocks.file_source(gr.sizeof_float,"fsink.dat")
        self.vsink = blocks.vector_sink_f()
        '''if __name__!="__main__":
           print "in if condition"
           fsource.seek(-250,2)'''
        t.connect(fsource,self.vsink)
        t.run()
        samples=scipy.array(self.vsink.data())
        self.vsink.reset()
        self.fsink.close()
        open("SineData.dat",'w').close()
        #sleep(0.05)
        self.fsink.open("fsink.dat")
        return samples


#!/usr/bin/python
'''
sender() is an optional method to monitor interference based off on received pkt's header
'''
def sender():
    try:

        interf = 0 # Counter
        interf_none = 0
        NF_none = 0
        interf_primaryoff = 0
        NF_primaryoff = 0

        while 1:
            input=(q1.get())
            if input[2] != '3' and input[2] != '8' and input[2] != 'None' and input[2] != 'Primary OFF':
                interf = interf + 1
            elif input[2] == 'Primary OFF':
                if input[3] == 0:
                    interf_primaryoff = interf_primaryoff + 1
                else:
                    NF_primaryoff = NF_primaryoff + 1
            elif input[2] == 'None':
                if input[3] == 0:
                    interf_none = interf_none + 1
                else:
                    NF_none = NF_none + 1
            else:
                interf_none, NF_none, interf = 0,0,0


            if interf_none == 6: #>= 2 and interf_none <= 5:
                sending = list(input[0:2])
                sending.extend(('INC',0,1,input[3]))
                sending = tuple(sending)
                q.put(sending)
                print 'interference checker send - ', sending
                interf_none = 0
            elif NF_none == 6: # >= 2 and NF_none <= 5:
                sending = list(input[0:3])
                sending.extend((0,0,input[3]))
                sending = tuple(sending)
                q.put(sending)
                print 'interference checker send - ', sending
                NF_none = 0
            elif interf == 2: # >= 2 and interf <= 5:
                sending = list(input[0:3])
                sending.extend((0,1,input[3]))
                sending = tuple(sending)
                q.put(sending)
                print 'interference checker send - ', sending
                #sleep(3)
                interf = 0
            elif interf_primaryoff == 6: #>= 2 and interf_none <= 5:
                sending = list(input[0:2])
                sending.extend(('INC',0,1,input[3]))
                sending = tuple(sending)
                q.put(sending)
                print 'interference checker send - ', sending
                interf_primaryoff = 0
            elif NF_primaryoff == 6: # >= 2 and NF_none <= 5:
                sending = list(input[0:3])
                sending.extend((0,0,input[3]))
                sending = tuple(sending)
                q.put(sending)
                print 'interference checker send - ', sending
                NF_primaryoff = 0
            elif interf_none > 6:
                interf_none = 0
            elif NF_none > 6:
                NF_none = 0
            elif interf_primaryoff > 6:
                interf_primaryoff = 0
            elif NF_primaryoff > 6:
                NF_primaryoff = 0
            #elif interf > 3:
            #    interf = 0


    except KeyboardInterrupt:
        sys.exit()

global n_rcvd, n_right, header, pktno
q = Queue.Queue() # sender puts, spike puts, client gets
q1 = Queue.Queue() # main puts, sender gets
q2 = Queue.Queue() # main puts, spike gets


### Main Function ###
def main():


    global n_rcvd, n_right, header, pktno
    header , pktno  = None, None
    n_rcvd = 0
    n_right = 0


    def rx_callback(ok, payload):
        global n_rcvd, n_right, header, pktno
        (pktno,) = struct.unpack('!H', payload[0:2])
        (header,) = struct.unpack('!c', payload[2:3])
        n_rcvd += 1
        if ok:
            n_right += 1

        if options.type=='Rx':
            print "Tx = %s  ok = %5s  pktno = %4d  n_rcvd = %4d  n_right = %4d" % (header,
            ok, pktno, n_rcvd, n_right)

    demods = digital.modulation_utils.type_1_demods()

    usage = "usage: %prog [options]"
    parser = OptionParser(option_class=eng_option, usage=usage, conflict_handler="resolve")
    expert_grp = parser.add_option_group("Expert")
    #usrp_options.add_rx_options(parser)

    ### Periodogram parameters ###
    parser.add_option("-d", "--decim", type="intx", default=400,
            help="set decimation to DECIM [default=%default]")
    parser.add_option("-F", "--fft-size", type="int", default=128,
            help="Specify number of FFT bins [default=%default]")
    parser.add_option("-b", "--noofbins", type="int", default=128,
                help="Specify number of bins to consider [default=%default]")
    parser.add_option("-N", "--nblocks", type="int", default=250,
            help="Specify size of Nblocks [default=%default]")
    ### For USRP2 and UHD ###
    parser.add_option("--scalarx", type="int", default=1000,
            help="Specify the scalar multiplier for USRP2 [default=%default]")

    parser.add_option("-a", "--args", type="string", default="",
                  help="UHD device address args [default=%default]")
    parser.add_option("", "--spec", type="string", default=None,
                  help="Subdevice of UHD device where appropriate")
    parser.add_option("-A", "--antenna", type="string", default=None,
                  help="select Rx Antenna where appropriate")
    parser.add_option("", "--rx-freq", type="eng_float", default=None,
                  help="set receive frequency to FREQ [default=%default]",
                  metavar="FREQ")
    parser.add_option("", "--lo-offset", type="eng_float", default=0,
                  help="set local oscillator offset in Hz (default is 0)")
    parser.add_option("", "--rx-gain", type="eng_float", default=None,
                  help="set receive gain in dB (default is midpoint)")
    parser.add_option("-C", "--clock-source", type="string", default=None,
                  help="select clock source (e.g. 'external') [default=%default]")
    ### You tell me what this is ###
    parser.add_option("--real-time", action="store_true", default=False,
            help="Attempt to enable real-time scheduling")

    parser.add_option("-m", "--modulation", type="choice", choices=demods.keys(),
                      default='psk',
                      help="Select modulation from: %s [default=%%default]"
                            % (', '.join(demods.keys()),))
    parser.add_option("","--from-file", default=None,
                      help="input file of samples to demod")

    parser.add_option("-t", "--type", type="string", default="Rx/S",
                  help="Select mode - Rx,S,Rx/S (default is Rx/S)")
    # Select Sensor
    parser.add_option("-s", "--sensor", type="string", default="S2",
                  help="Select mode - S1,S2 (default is S2)")

    parser.add_option("-P", "--pfa", type="eng_float", default=0.05,
		     				help="choose the desired value for Probability of False\
		     				Alarm [default=%default]")



    #usrp_options._add_options(parser)
    receive_path.add_options(parser, expert_grp)
    uhd_receiver.add_options(parser)
    #  transmit_path.add_options(parser, expert_grp)
    #  uhd_transmitter.add_options(parser)



    (options, args) =  parser.parse_args()

    for mod in demods.values():
        mod.add_options(expert_grp)


    if len(args) != 0:
        parser.print_help(sys.stderr)
        sys.exit(1)


    if options.from_file is None:
        if options.rx_freq is None:
            sys.stderr.write("You must specify -f FREQ or --freq FREQ\n")
            parser.print_help(sys.stderr)
            sys.exit(1)


    #start ignore
    if not options.real_time:
        realtime = False
    else:
        # Attempt to enable realtime scheduling
        r = gr.enable_realtime_scheduling()
        if r == gr.RT_OK:
            realtime = True
        else:
            realtime = False

        print "Note: failed to enable realtime scheduling"
    print options
    store_pkt = []
    tb = powerestimator(demods[options.modulation], rx_callback,options)
    try:
        tb.start()
        if options.type=='S' or options.type=='Rx/S':
            #Start the flow graph(in another thread...) and wait for a minute
            counter = 1
            skip = 1
            while 1:
                sleep(7)

                #Calculate mean and variance
                samples = tb.d.get_data()
                if len(samples) == 0:
                    #print 'Terminating operation because RSSI = NaN!!!!!!!!!!!!!'
                    continue
                spectrumdecision = 0

                if skip == 1:
                    skip = 0
                    continue

                randomvariablearray = []
                N = options.nblocks
                '''
                while(len(samples) >= N):
                    temparray = samples[0:N]
                    randomvariablearray.append(temparray.mean())
                    samples = samples[N:]
                '''
                store_pkt.append(pktno)
                if len(store_pkt) > 4:
                    del store_pkt[0:(len(store_pkt)-4)]

                mean = scipy.array(samples).mean()
                variance = scipy.array(samples, dtype = scipy.float64).var()
                #print len(samples)
                print '*'*80
                print 'Mean = ', 10*math.log10(mean), '\t\t\tVariance = ',10*math.log10(variance)


                q.put((options.args[-1],10*math.log10(mean),10*math.log10(variance)))



        tb.wait()
            #del tb
    except KeyboardInterrupt:
        tb.stop()
        print 'SIGTERM received.'




class clientthread(threading.Thread):

    def __init__(self,client_sock):
        self.s = client_sock
        threading.Thread.__init__(self)
        self.stoprequest = False
        self.q = q
    def run(self):
        try:
            self.s.connect((host,8888))
            print 'connected.........................'
        except socket.error as e:
            print 'Not Connected : '+str(e)
            sys.exit()

        while not self.stoprequest:

            queue_tuple = self.q.get()


            if len(queue_tuple) == 3:
                msg_tosend = ','.join((str(queue_tuple[0]),str(queue_tuple[1]),str(queue_tuple[2])
                                   ))
            elif len(queue_tuple) == 4:
                msg_tosend = ','.join((str(queue_tuple[0]),str(queue_tuple[1]),str(queue_tuple[2]),str(queue_tuple[3])
                                   ,str(queue_tuple[4])))
            else:
                msg_tosend = ','.join((str(queue_tuple[0]),str(queue_tuple[1]),str(queue_tuple[2]),str(queue_tuple[3])
                                   ,str(queue_tuple[4]),str(queue_tuple[5])))



            print '\nsending - ',msg_tosend
            try:
                self.s.sendall(msg_tosend)
                #if str(queue_tuple[4]) == '1':
                #    sleep(4)

            except socket.error as e:
                print 'Not sent' + str(e)
                if str(e) == '[Errno 32] Broken pipe' or str(e) == '[Errno 104] Connection reset by peer':
                    print 'Cancel sending'
                    sys.exit()

            except KeyboardInterrupt:
                print '\nSIGTERM received.'
                self.join()



if __name__ == "__main__":
    client_sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    print 'socket created...'
    host = '192.168.10.20'
    #host = 'localhost'

    t2 = clientthread(client_sock)
    t2.daemon = True
    t2.start()

    print 'done!'
    try:
        main()
    except RuntimeError as err:
	print '******************************',err.message
	if 'No devices found' in err.message:
            regx = re.compile('\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',re.MULTILINE )
            ip_str = regx.search(err.message).group()
	    
            subprocess.Popen(shlex.split('notify-send -t 2000 "Device with IP %s not found"' %ip_str))
	    subprocess.Popen(shlex.split('killall python -u %s'%(getpass.getuser())))

############ PID=$! contains last process' pid##################################



