# How a browser turns a URL into a page

First, navigation begins when a person requests a page, and the browser finds the server's IP address through DNS, reusing a cached result when one is available.

Next, after the browser establishes a TCP connection, TLS verifies the server for HTTPS and establishes a secure connection before content transfer begins.

Once the connection is ready, the browser sends an initial HTTP GET request, and the server replies with response headers and the contents of the HTML document.

As HTML arrives, the browser tokenizes the markup and builds a DOM tree, while linked stylesheets, scripts, images, and other resources can trigger more requests.

Finally, the browser combines the DOM and CSSOM into a render tree, computes layout for visible elements, and paints the resulting pixels to the screen.

Primary references:

- MDN, "Populating the page: how browsers work": https://developer.mozilla.org/en-US/docs/Web/Performance/Guides/How_browsers_work
- MDN, "How browsers load websites": https://developer.mozilla.org/en-US/docs/Learn_web_development/Getting_started/Web_standards/How_browsers_load_websites
