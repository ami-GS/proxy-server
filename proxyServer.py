import sys
import socket
import json

import tornado.httpserver
import tornado.ioloop
import tornado.iostream
import tornado.web
import tornado.httpclient

#TODO fix bug when black and/or white List filters are applied
#TODO fix bug of asynchronous when filters are used

try:
    import redis
    r = redis.Redis(host="127.0.0.1", port=6379, db=0)
    r.rpush("test", "test")
    r.delete("test")
except:
    r = None

blackList = []
whiteList = []
debug_mode = False

class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS", "CONNECT")

    def initialize(self):
        pass

    @tornado.web.asynchronous
    def requestHandler(self, request):
        self.sendRequest(request)

    @tornado.web.asynchronous
    def handle_response(self, response):
        if self.useFilter("black", "content"):
            self.finish(); return

        if response.code == 599:
            return #for dropbox notification
        if response.error and not isinstance(response.error, tornado.httpclient.HTTPError):
            self.set_status(500)
            self.write('Internal server error:\n' + str(response.error))
        else:
            if enableCache and not r.exists(self.request.uri):
                self._setCache(response)
            self.set_status(response.code)

            for header in ('Date', 'Cache-Control', 'Server', 'Content-Type', 'Location'):
                v = response.headers.get(header)
                if v:
                    self.set_header(header, v)
            if response.body:
                self.write(response.body)
            if response.code == 304:
                self.flush()
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
        if self.useFilter("black", "url"):
            self.finish(); return
        if self.useFilter("white", "url"):
            self.finish(); return
        if debug_mode and enableCache and r.exists(self.request.uri):
            print("return cache!")
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
        if self.useFilter("black", "url"):
            self.finish(); return
        if self.useFilter("white", "url"):
            self.finish(); return
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

    @tornado.web.asynchronous
    def useFilter(self, filter="black", type="url"):
        def denyRequest():
            self.set_status(403)
            self.write("Forbidden %s" % type)

        if filter == "black" and blackList:
            if True in [url in self.request.uri for url in blackList[type]]:
                denyRequest()
                return True
        elif filter == "white" and whiteList:
            if True not in [url in self.request.uri for url in whiteList[type]]:
                denyRequest()
                return True
        return False


def run_proxy(port, enableCache):
    app = tornado.web.Application([
        (r'.*', ProxyHandler,),
    ])
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.start()

def getFilter(filtType):
#    global whiteList, blackList
    def readFile(file):
        with open("./filters/"+file+"List.txt", "r") as f:
            return json.loads(f.read())

    return readFile(filtType)

def setParam(paramType):
    port = 8080
    global whiteList, blackList
    enableCache = False
    comment = "Starting HTTP proxy on port %d\n"
    if paramType.count("c"):
        if not r:
            print("please install python redis client.")
        else:
            enableCache = True
            comment += "Cache enabled\n"
            if args.index("init"):
                r.flushall()
    if paramType.count("p"):
        try:
            for i in range(2, len(args)):
                port = int(args[i])
        except (ValueError, IndexError) as e:
            pass
    if paramType.count("b"):
        blackList = getFilter("black")
        comment += "Blacklist enabled\n"
    if paramType.count("w"):
        whiteList = getFilter("white")
        comment += "Whitelist enabled\n"
    if paramType.count("debug"):
        print("debug mode enabled!!")
        global debug_mode
        debug_mode = True

    return comment, enableCache, port

if __name__ == '__main__':
    args = sys.argv

    param = ""
    if len(args) >= 2:
        for arg in args:
            if arg.count("-"):
                param += arg[1:]

    comment, enableCache, port = setParam(param)

    print(comment % port)
    run_proxy(port, enableCache)
