import sys
import socket

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient
import redis

r = redis.Redis(host="127.0.0.1", port=6379, db=0)
r.flushall()

class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS", "CONNECT")

    def initialize(self):
        pass

    @tornado.web.asynchronous
    def requestHandler(self, request):
        if black:
            if True in [url in self.request.uri for url in blackList]:
                self.denyRequest()
                return
        if white:
            if True in [url not in self.request.uri for url in whiteList]:
                self.denyRequest()
                return
        self.sendRequest(request)

    @tornado.web.asynchronous
    def denyRequest(self):
        self.set_status(403)
        self.write("Forbidden")
        self.finish()

    @tornado.web.asynchronous
    def handle_response(self, response):
        print response.code
        if response.code == 599:
            return #for dropbox notification
        if response.error and not isinstance(response.error, tornado.httpclient.HTTPError):
            self.set_status(500)
            self.write('Internal server error:\n' + str(response.error))
        else:
            if not r.exists(self.request.uri):
                self._setCache(response)
            self.set_status(response.code)

            for header in ('Date', 'Cache-Control', 'Server', 'Content-Type', 'Location'):
                v = response.headers.get(header)
                if v:
                    self.set_header(header, v)
            if response.body:
                self.write(response.body)
            self.finish()

    @tornado.web.asynchronous
    def sendRequest(self, request):
        req = tornado.httpclient.HTTPRequest(
              url=request.uri,
              method=request.method, body=request.body,
              headers=request.headers, follow_redirects=False,
              allow_nonstandard_methods=True)
        client = tornado.httpclient.AsyncHTTPClient()
        try:
            client.fetch(req, self.handle_response)
        except tornado.httpclient.HTTPError as e:
            if hasattr(e, 'response') and e.response:
                self.handle_response(e.response)
            else:
                self.set_status(500)
                self.write('Internal server error:\n' + str(e))
                self.finish()

    @tornado.web.asynchronous
    def _getCache(self, response):
        self.set_status(int(response[0]))
        for i in range(2, len(response), 2):
            self.set_header(response[i], response[i+1])
        if self.get_status() != 304:
            self.write(response[1])
        self.finish()

    @tornado.web.asynchronous
    def _setCache(self, response):
        query = [response.code]
        query.append(response.body)
        for header in ('Date', 'Cache-Control', 'Server', 'Content-Type', 'Location'):
            v = response.headers.get(header)
            if v:
                query.append(header)
                query.append(v)

        for q in query:
            r.rpush(self.request.uri, q)
        r.expire(self.request.uri, 100)

    @tornado.web.asynchronous
    def get(self):
        if enableCache and r.exists(self.request.uri):
            print "return cache!"
            self._getCache(r.lrange(self.request.uri, 0, -1))
        else:
            return self.requestHandler(self.request)
    @tornado.web.asynchronous
    def post(self):
        return self.requestHandler(self.request)
    @tornado.web.asynchronous
    def head(self):
        return self.requestHandler(self.request)#same as GET, but it returns only HTTP header
    @tornado.web.asynchronous
    def delete(self):
        return self.requestHandler(self.request)#delete file located in  server by specifing URI
    @tornado.web.asynchronous
    def patch(self):
        return self.requestHandler(self.request)#same as put, but it changes only difference
    @tornado.web.asynchronous
    def put(self):
        return self.requestHandler(self.request)#replace file located in server by specifing URI
    @tornado.web.asynchronous
    def options(self):
        return self.requestHandler(self.request)#notification of trasfer option
    @tornado.web.asynchronous
    def connect(self):
        host, port = self.request.uri.split(':')
        client = self.request.connection.stream

        def read_from_client(data):
            upstream.write(data)

        def read_from_upstream(data):
            client.write(data)

        def client_close(data=None):
            if upstream.closed():
                return
            if data:
                upstream.write(data)
            upstream.close()

        def upstream_close(data=None):
            if client.closed():
                return
            if data:
                client.write(data)
            client.close()

        def start_tunnel():
            client.read_until_close(client_close, read_from_client)
            upstream.read_until_close(upstream_close, read_from_upstream)
            client.write(b'HTTP/1.1 200 Connection established\r\n\r\n')

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        upstream = tornado.iostream.IOStream(s)
        upstream.connect((host, int(port)), start_tunnel)

 

def run_proxy(port, black, white, enableCache):
    if black or white:
        setFilter(black, white)

    app = tornado.web.Application([
        (r'.*', ProxyHandler,),
    ])
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.start()

whiteList = []
blackList = []
def setFilter(black, white):
    global whiteList, blackList
    def readFile(file):
        with open(file, "r") as f:
            return [line.split("\n")[0] for line in f.readlines()]

    if white:
        whiteList = readFile("./filters/whiteList.txt")
    if black:
        blackList = readFile("./filters/blackList.txt")


if __name__ == '__main__':
    port = 8888
    black = False
    white = False
    enableCache = False
    if len(sys.argv) >= 2:
        if sys.argv.count("-c"):
            enableCache = True
        if sys.argv.count("-p"):
            port = int(sys.argv[sys.argv.index("-p")+1])
        if sys.argv.count("-b"):
            black = True
        if sys.argv.count("-w"):
            white = True


    print ("Starting HTTP proxy on port", port)
    run_proxy(port, black, white, enableCache)
