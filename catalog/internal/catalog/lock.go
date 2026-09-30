package catalog

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"regexp"
	"sort"
	"strings"
)

// LockFile is the name of the images lock that goes with a manifest.
const LockFile = "images.lock.json"

var (
	digestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)
)

// Lock pins the published case image of each task of one dataset version by
// digest. `ssebench dataset lock` writes it; its JSON Schema is
// datasets/schema/images-lock.schema.json.
type Lock struct {
	Dataset string                 `json:"dataset"`
	Version string                 `json:"version"`
	Images  map[string]LockedImage `json:"images"`
}

// LockedImage is a published case image.
type LockedImage struct {
	// Digest of the image in the registry.
	Digest string `json:"digest"`
	// FilesSHA256 is the FilesDigest of the task's files that the image was built from.
	FilesSHA256 string `json:"files_sha256"`
	// Revision is the commit that the image was built and verified at.
	Revision string `json:"revision"`
}

// LoadLock reads an images lock file.
func LoadLock(path string) (Lock, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return Lock{}, err
	}
	l, err := ParseLock(content)
	if err != nil {
		return Lock{}, fmt.Errorf("%s: %w", path, err)
	}
	return l, nil
}

// ParseLock decodes an images lock and checks its fields. Unknown fields are
// errors, as in Parse.
func ParseLock(content []byte) (Lock, error) {
	dec := json.NewDecoder(bytes.NewReader(content))
	dec.DisallowUnknownFields()
	var l Lock
	if err := dec.Decode(&l); err != nil {
		return Lock{}, err
	}

	var errs []error
	if l.Dataset == "" || l.Version == "" {
		errs = append(errs, errors.New("dataset and version are required"))
	}
	if l.Images == nil {
		errs = append(errs, errors.New("images is required"))
	}
	for id, image := range l.Images {
		if !digestPattern.MatchString(image.Digest) {
			errs = append(errs, fmt.Errorf("image of task %q has no valid digest", id))
		}
		if !sha256Pattern.MatchString(image.FilesSHA256) {
			errs = append(errs, fmt.Errorf("image of task %q has no valid files_sha256", id))
		}
	}
	if err := errors.Join(errs...); err != nil {
		return Lock{}, err
	}
	return l, nil
}

// FilesDigest identifies the files of a task: the SHA-256 of the JSON object
// that maps each path to its checksum, keys sorted, without whitespace and
// with every character outside printable ASCII escaped. That is the text that
// ssebench's files_digest hashes, so both compute the same value.
func FilesDigest(files map[string]string) string {
	keys := make([]string, 0, len(files))
	for k := range files {
		keys = append(keys, k)
	}
	sort.Strings(keys)

	var b strings.Builder
	b.WriteByte('{')
	for i, k := range keys {
		if i > 0 {
			b.WriteByte(',')
		}
		writeASCIIString(&b, k)
		b.WriteByte(':')
		writeASCIIString(&b, files[k])
	}
	b.WriteByte('}')
	sum := sha256.Sum256([]byte(b.String()))
	return hex.EncodeToString(sum[:])
}

func writeASCIIString(b *strings.Builder, s string) {
	b.WriteByte('"')
	for _, r := range s {
		switch {
		case r == '"':
			b.WriteString(`\"`)
		case r == '\\':
			b.WriteString(`\\`)
		case r == '\n':
			b.WriteString(`\n`)
		case r == '\r':
			b.WriteString(`\r`)
		case r == '\t':
			b.WriteString(`\t`)
		case r == '\b':
			b.WriteString(`\b`)
		case r == '\f':
			b.WriteString(`\f`)
		case r >= 0x20 && r <= 0x7e:
			b.WriteRune(r)
		case r > 0xffff:
			r -= 0x10000
			fmt.Fprintf(b, `\u%04x\u%04x`, 0xd800+(r>>10), 0xdc00+(r&0x3ff))
		default:
			fmt.Fprintf(b, `\u%04x`, r)
		}
	}
	b.WriteByte('"')
}

// Pinned returns the digest that lock pins for the task. There is none when
// the lock is nil or for another dataset version, does not list the task, or
// lists it for an image built from other files than the ones the manifest
// gives the task: it would be another task's image.
func (m Manifest) Pinned(lock *Lock, t Task) (string, bool) {
	if lock == nil || lock.Dataset != m.Dataset || lock.Version != m.Version {
		return "", false
	}
	image, ok := lock.Images[t.ID]
	if !ok || (t.Files != nil && FilesDigest(t.Files) != image.FilesSHA256) {
		return "", false
	}
	return image.Digest, true
}

// Resolve returns the task with its image names resolved as Task.Resolve does,
// naming the case image by the digest that lock pins for it, if any, and
// otherwise by the dataset version as its tag.
func (m Manifest) Resolve(t Task, registry string, lock *Lock) Task {
	digest, _ := m.Pinned(lock, t)
	return t.Resolve(registry, m.Version, digest)
}
