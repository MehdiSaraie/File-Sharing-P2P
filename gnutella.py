import os, time
from twisted.internet import reactor, protocol
from twisted.protocols import basic

from constants import *
import globals
import utility
import difflib

"""
GNUTELLA TWISTED CLASSES
"""
class GnutellaProtocol(basic.LineReceiver):
	def __init__(self):
		self.output = None
		self.normalizeNewlines = True
		self.initiator = False
		self.verified = True
		self.lastReceivedChunk = {}

	def setInitiator(self):
		self.initiator = True
		self.verified = False

	def connectionMade(self):
		globals.connections.append(self)
		peer = self.transport.getPeer()
		if (globals.ui != None):
			globals.ui.addPeerToListWidget(peer.host, peer.port)
		utility.writeLog("Connected to {0}:{1}\n".format(peer.host, peer.port))
		if self.initiator:
			self.transport.write("GNUTELLA CONNECT/0.4\n{0}\n$$$".format(globals.myPort).encode('utf-8'))
			utility.writeLog("Sending GNUTELLA CONNECT to {0}:{1}\n".format(peer.host, peer.port))
		host = self.transport.getHost()
		globals.myIP = host.host

	def connectionLost(self, reason):
		globals.connections.remove(self)
		peer = self.transport.getPeer()
		if (globals.ui != None):
			globals.ui.removePeerFromListWidget(peer.host, peer.port)
		utility.writeLog("Disconnected with {0}:{1}\n".format(peer.host, peer.port))
		utility.makePeerConnection()

	def dataReceived(self, data):
		data = bytes.decode(data)
		lines = data.split("$$$")
		for line in lines:
			if (len(line) > 0):
				self.handleMessage(line)

	def handleMessage(self, data):
		peer = self.transport.getPeer()
		if(data.startswith("GNUTELLA CONNECT")):
			self.peerPort = int(data.split('\n')[1])
			utility.writeLog("Received GNUTELLA CONNECT from {0}:{1}\n".format(peer.host, peer.port))
			if(len(globals.connections) <= MAX_CONNS):
				self.transport.write("GNUTELLA OK\n{0}\n$$$".format(globals.myPort).encode('utf-8'))
				utility.writeLog("Sending GNUTELLA OK to {0}:{1}\n".format(peer.host, peer.port))
			else:
				self.transport.write("WE'RE OUT OF NUTELLA\n$$$".encode('utf-8'))
				utility.writeLog("Sending WE'RE OUT OF NUTELLA to {0}:{1}\n".format(peer.host, peer.peer))
		elif (self.initiator and not self.verified):
			if(data.startswith("GNUTELLA OK")):
				self.peerPort = int(data.split('\n')[1])
				utility.writeLog("Connection with {0}:{1} verified\n".format(peer.host, peer.port))
				self.verified = True
				self.sendPing()
			else:
				utility.writeLog("Connection with {0}:{1} rejected\n".format(peer.host, peer.port))
				reactor.stop()
		else:
			utility.writeLog("\n")
			message = data.split('&', 3)
			msgid = message[0]
			payloadDesc = int(message[1])
			ttl = int(message[2])
			payload = message[3]
			if(payloadDesc == 0):
				utility.writeLog("Received PING: msgid={0} ttl={1}\n".format(msgid, ttl))
				self.handlePing(msgid, ttl)
			elif(payloadDesc == 1):
				utility.writeLog("Received PONG: msgid={0} payload={1}\n".format(msgid, payload))
				self.handlePong(msgid, payload)
			elif(payloadDesc == 80):
				utility.writeLog("Received Query: msgid={0} ttl={1} query={2}\n".format(msgid, ttl, payload))
				self.handleQuery(msgid, ttl, payload)
			elif(payloadDesc == 161):
				utility.writeLog("Received FileChunk: msgid={0} payload={1}\n".format(msgid, payload))
				self.handleFileChunk(msgid, payload)
			elif(payloadDesc == 170):
				utility.writeLog("Received SimilarFiles: msgid={0} ttl={1} payload={2}\n".format(msgid, ttl, payload))
				self.handleSimilarFiles(msgid, ttl, payload)

	def buildHeader(self, descrip, ttl):
		header = "{0}{1:03}".format(globals.nodeID, globals.msgID)
		globals.msgID += 1
		if(globals.msgID > 999):
			globals.msgID = 0
		return "{0}&{1}&{2}&".format(header, descrip, ttl) 

	def sendPing(self, msgid=None, ttl=7):
		if(ttl <= 0):
			return
		if msgid:
			message = "{0}&{1}&{2}&".format(msgid, "00", ttl)
			utility.writeLog("Forwarding PING: {0}\n".format(message))
		else:
			message = self.buildHeader("00", ttl)
			utility.writeLog("Sending PING: {0}\n".format(message))
		message = "{0}$$$".format(message)
		for cn in globals.connections:
			if(msgid == None or cn != self):
				cn.transport.write(message.encode('utf-8'))

	def sendPong(self, msgid, payload=None):
		IP = self.transport.getHost().host
		header = "{0}&{1}&{2}&".format(msgid, "01", 7)
		if payload:
			message = "{0}{1}$$$".format(header, payload)
			utility.writeLog("Forwarding PONG: {0}\n".format(message))
		else:
			message = "{0}{1}&{2}$$$".format(header, globals.myPort, IP)
			utility.writeLog("Sending PONG: {0}\n".format(message))
		globals.msgRoutes[msgid][0].transport.write(message.encode('utf-8'))

	def handlePing(self, msgid, ttl):
		#send pong, store data, forward ping
		if utility.isValid(msgid):
			return
		globals.msgRoutes[msgid] = (self, time.time())
		self.sendPong(msgid)
		self.sendPing(msgid, ttl-1)

	def handlePong(self, msgid, payload):
		info = payload.split("&")
		node_data = (int(info[0]), info[1])
		if info not in globals.netData:
			globals.netData.append(node_data)
		if(msgid.startswith(globals.nodeID)):
			utility.makePeerConnection(node_data[1], node_data[0])
		else:
			self.sendPong(msgid, payload)
			utility.makePeerConnection()

	def sendQuery(self, query, msgid=None, ttl=7):
		if (globals.ui != None):
			globals.ui.flushSimilarsListWidget()
		if(ttl <= 0):
			return
		if(msgid):
			header = "{0}&80&{1}&".format(msgid, ttl)
		else:
			header = self.buildHeader(80, ttl)
		message = "{0}{1}$$$".format(header, query)
		for cn in globals.connections:
			if(msgid == None or cn != self):
				cn.transport.write(message.encode('utf-8'))

	def handleQuery(self, msgid, ttl, query):
		if utility.isValid(msgid):
			return
		globals.msgRoutes[msgid] = (self, time.time())
		if "../" in query:
			print("Cannot request files in upper directories")
			return
		
		dir_list = os.listdir(globals.directory)
		most_similar_contents = difflib.get_close_matches(query, dir_list)
		print(most_similar_contents)
		self.sendSimilarFiles(msgid, most_similar_contents)

		filepath = os.path.join(globals.directory, query)
		if os.path.isfile(filepath):
			print(filepath)
			utility.writeLog("File found: {0}; Sending File\n".format(query))
			passedNodes = ""
			fp = open(filepath, "r")
			chunkNumber = 1
			fileSize = os.path.getsize(filepath)
			while True:
				fileChunk = fp.read(CHUNK_SIZE)
				if (fileChunk == ""):
					break
				payload = "{0}&{1}&{2}&{3}&{4}".format(query, fileSize, passedNodes, chunkNumber, fileChunk)
				self.sendFileChunk(msgid, payload)
				chunkNumber += 1
				
			fp.close()
		else:
			self.sendQuery(query, msgid, ttl-1)
			utility.writeLog("Forwarding Query: {0} {1}".format(query, msgid))

	def handleSimilarFiles(self, msgid, ttl, similar_files):
		similar_files_list = similar_files.split("+")
		if (globals.ui != None):
			globals.ui.addSimilarFilesListWidget(similar_files_list)

	def sendFileChunk(self, msgid, payload):
		header = "{0}&161&7&".format(msgid)
		if not utility.isValid(msgid):
			return
		message = "{0}{1}$$$".format(header, payload)
		globals.msgRoutes[msgid][0].transport.write(message.encode('utf-8'))
	
	def sendSimilarFiles(self, msgid, file_names):
		header = "{0}&170&7&".format(msgid)
		if not utility.isValid(msgid):
			return
		message = "{0}{1}$$$".format(header, "+".join(file_names))
		globals.msgRoutes[msgid][0].transport.write(message.encode('utf-8'))

	def handleFileChunk(self, msgid, payload):
		peer = self.transport.getPeer()
		info = payload.split('&', 4)
		query = info[0]
		fileSize = int(info[1])
		info[2] += "{0}:{1} -> ".format(peer.host, peer.port)
		passedNodes = info[2]
		chunkNumber = int(info[3])
		fileChunk = info[4]
		filepath = os.path.join(globals.directory, query)
		if(msgid.startswith(globals.nodeID)):
			if(chunkNumber != self.lastReceivedChunk.get(msgid, 0) + 1):
				return
			self.lastReceivedChunk[msgid] = chunkNumber
			host = self.transport.getHost()
			passedNodes += "{0}:{1}".format(host.host, host.port)
			print("Chunk {0} received from path: {1}".format(chunkNumber, passedNodes))
			if chunkNumber == 1:
				self.time = 0
			fp = open(filepath, "a+")
			fp.write(fileChunk)
			fp.close()
			downloadedSize = (chunkNumber-1) * CHUNK_SIZE + len(fileChunk)
			isLastChunk = downloadedSize == fileSize or len(fileChunk) < CHUNK_SIZE
			now = time.time()
			speed = len(fileChunk) // (now - self.time)
			self.time = now
			if (isLastChunk):
				if (globals.ui != None):
					globals.ui.socketSignal.emit("updateProgressBar&{0}&{1}".format(100, speed))
				utility.printLine("File Download Completed")
			else:
				if (globals.ui != None):
					globals.ui.socketSignal.emit("updateProgressBar&{0}&{1}".format(downloadedSize*100//fileSize, speed))
		else:
			payload = "&".join(info)
			self.sendFileChunk(msgid, payload)

class GnutellaFactory(protocol.ReconnectingClientFactory):
	def __init__(self, isInitiator=False):
		self.initiator = isInitiator

	def buildProtocol(self, addr):
		prot = GnutellaProtocol()
		if self.initiator:
			prot.setInitiator()
		return prot
 
	def startedConnecting(self, connector):
		self.host = connector.host
		self.port = connector.port
		utility.writeLog("Trying to connect to {0}:{1}\n".format(self.host, self.port))

	def clientConnectionFailed(self, transport, reason):
		utility.writeLog("Retrying connection with %s:%s\n" % (transport.host, transport.port))
		numConns = len(globals.connections)
		if numConns == 0:
			utility.makePeerConnection()
