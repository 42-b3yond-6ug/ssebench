use ammonia::Builder;

fn main() {
    let payload = r#"
<svg>
  <iframe>
    <a title="</iframe><img src=x onerror=alert('XSS')>">
      test
    </a>
</svg>
"#;

    let cleaned = Builder::new()
        // Key point: explicitly allow both SVG and iframe tags
        .add_tags(&["svg", "iframe", "a", "img"])
        // Intentionally relax attribute restrictions for teaching/demo purposes
        .add_generic_attributes(&["title", "src", "onerror"])
        .clean(payload)
        .to_string();

    println!("===== Original Input =====");
    println!("{}", payload);

    println!("\n===== Sanitized Output =====");
    println!("{}", cleaned);
}

