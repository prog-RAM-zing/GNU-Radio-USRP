__author__ = 'Kishan'

import socket
import sqlite3
import asyncore
import datetime
import sys
import threading
from time import sleep
from ETA_merger import *

global sensor_list

#Change sensorlist depending on the IP address identifier for each device and number of devices
sensor_list = [1,2,3,4]
database = 'database_name.dba'

def analysis():


    global sensor_list
    analysis_time = 2 # Minutes

    while(1):
        sleep(analysis_time*60)
        results = main_function(database)
	with open('results.txt','w') as f1:
 	    print >> f1, results
        conn.execute('DELETE FROM  Signal_Strength_Temporary WHERE Noise!=1')


t1 = threading.Thread(target=analysis)
t1.daemon=True
t1.start()


conn  = sqlite3.connect('/path/to/database/'+database,check_same_thread=False)
class Server(asyncore.dispatcher):
    def __init__(self, host = '', port = 8888 ):
        asyncore.dispatcher.__init__(self)
        self.host = host
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        print 'Listening on port : %d\n' %port
        self.listen(1)


    def handle_accept(self):
        # when we get a client connection start a dispatcher for that
        # client
        item = self.accept()
        if item is None:

            return
        socket, address = item[0],item[1]
        print 'Connection by', address
        EchoHandler(socket)





class EchoHandler(asyncore.dispatcher_with_send):

    def handle_read(self):
        global sensor_list

        try:
            incoming = self.recv(1024)
            if incoming:
                #x =  str(datetime.datetime.now())
                #time_1 = x.split(' ')[-1].split(':')


                data_recvd = incoming.split(',')
                sensor_list[int(data_recvd[0])-1] = data_recvd
                #print data_recvd,'\t\t',sensor_list,'\n'
                if 1 not in sensor_list and 2 not in sensor_list and 3 not in sensor_list and 4 not in sensor_list:
                    timestamp =  str(datetime.datetime.now())
                    try:
                        with open('temp','r') as f1:
                            pass
                        for i in sensor_list:
                            conn.execute('insert into Signal_Strength(Noise,Sensor_Id,RSSI_Mean,RSSI_Variance,Timestamp) VALUES(?,?,?,?,?)',(1,i[0],float(i[1]),float(i[2]),timestamp))
                            conn.execute('insert into Signal_Strength_Temporary(Noise,Sensor_Id,RSSI_Mean,RSSI_Variance,Timestamp) VALUES(?,?,?,?,?)',(1,i[0],float(i[1]),float(i[2]),timestamp))
			    print float(i[1])
                        print '\t\t\t\tStored in Database - NOISE'
                    except IOError:
                        for i in sensor_list:
                            conn.execute('insert into Signal_Strength(Sensor_Id,RSSI_Mean,RSSI_Variance,Timestamp) VALUES(?,?,?,?)',(i[0],float(i[1]),float(i[2]),timestamp))
                            conn.execute('insert into Signal_Strength_Temporary(Sensor_Id,RSSI_Mean,RSSI_Variance,Timestamp) VALUES(?,?,?,?)',(i[0],float(i[1]),float(i[2]),timestamp))
			    print float(i[1])
                        print '\t\t\t\tStored in Database'
                    conn.commit()
                    sensor_list = [1,2,3,4]
                    
            return

        except KeyboardInterrupt:
            print  'SIGTERM received.\n'


server_port = 8888

s = Server(port=server_port)
try:
    asyncore.loop()
except KeyboardInterrupt:
    print "\nServer stopped. Ba-bye! :'(\n"

