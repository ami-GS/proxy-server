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

    @tornado.web.asynchronous
    def requestHandler(self, request):
        def handle_response(response):
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

        if r.exists(request.uri):
            print "return cache !!"
            self._getCache(r.lrange(request.uri,0,-1))
        else:
            req = tornado.httpclient.HTTPRequest(
                  url=request.uri,
                  method=request.method, body=request.body,
                  headers=request.headers, follow_redirects=False,
                  allow_nonstandard_methods=True)
            client = tornado.httpclient.AsyncHTTPClient()
            try:
                client.fetch(req, handle_response)
            except tornado.httpclient.HTTPError as e:
                if hasattr(e, 'response') and e.response:
                    handle_response(e.response)
                else:
                    self.set_status(500)
                    self.write('Internal server error:\n' + str(e))
                    self.finish()

    @tornado.web.asynchronous
    def _getCache(self, response):
        #print response
        self.set_status(int(response[0]))
        if response[2]:
            self.set_header(response[1], response[2])
        if response[3]:
            self.write(response[3])
        self.finish()

    @tornado.web.asynchronous
    def _setCache(self, response):
        r.rpush(self.request.uri, response.code)    #response code
        for header in ('Date', 'Cache-Control', 'Server', 'Content-Type', 'Location'):
            v = response.headers.get(header)
            if v:
                r.rpush(self.request.uri, header)   #header name
                r.rpush(self.request.uri, v)        #header info
                break
        r.rpush(self.request.uri, response.body)    #content
        r.expire(self.request.uri, 100)         #delete cache in 100 second

    @tornado.web.asynchronous
    def get(self):
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

 

def run_proxy(port):
    app = tornado.web.Application([
        (r'.*', ProxyHandler),
    ])
    app.listen(port)
    ioloop = tornado.ioloop.IOLoop.instance()
    ioloop.start()

if __name__ == '__main__':
    port = 8888
    if len(sys.argv) > 1:
        port = int(sys.argv[1])

    print ("Starting HTTP proxy on port", port)
    run_proxy(port)
