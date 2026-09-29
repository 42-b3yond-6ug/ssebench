### Description

**Summary: full access to the host's OS file system using `osfs.FS` with `Router.Static`**

Static file serving using `router.Static` and `osfs.FS` allows clients to access any file on the host file system using relative paths because the requested path is not sanitized and `.` and `..` segments are accepted. The files will be returned as a response, provided the system user running the Go application has read access to the requested file.

### Reproduction

```go
import (
	"goyave.dev/goyave/v5"
	"goyave.dev/goyave/v5/util/fsutil/osfs"
)

func Register(server *goyave.Server, router *goyave.Router) {
	fs, err := (&osfs.FS{}).Sub("resources")
	if err != nil {
		//...
		return
	}
	router.Static(fs, "/resources", false)
}
```

```
curl http://localhost:8080/resources/../../some/file
```
