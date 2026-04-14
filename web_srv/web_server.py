#!/usr/bin/env python3
"""
Web server initialization script.
Generates test files and starts Nginx.
"""
import os
import subprocess
import sys

def generate_test_files():
    """Generate test files in /home/files directory."""
    files_dir = "/home/files"
    os.makedirs(files_dir, exist_ok=True)
    
    # Small test file
    with open(f"{files_dir}/test.txt", "w") as f:
        f.write("This is a test file for web server.\n")
    
    # Medium file (1MB)
    with open(f"{files_dir}/medium.bin", "wb") as f:
        f.write(b"A" * (1024 * 1024))
    
    # Large file (10MB)
    with open(f"{files_dir}/large.bin", "wb") as f:
        f.write(b"B" * (10 * 1024 * 1024))
    
    # HTML file
    with open(f"{files_dir}/index.html", "w") as f:
        f.write("""<html>
                <head><title>Web Server</title></head>
                <body>
                <h1>Web Server Running</h1>
                <p>This is a test web server for traffic generation.</p>
                <ul>
                <li><a href="test.txt">test.txt</a> - Small text file</li>
                <li><a href="medium.bin">medium.bin</a> - 1MB binary file</li>
                <li><a href="large.bin">large.bin</a> - 10MB binary file</li>
                </ul>
                </body>
                </html>""")
    
    print("Test files generated in /home/files")

def start_nginx():
    """Start Nginx server."""
    print("Starting Nginx...")
    try:
        subprocess.run(["nginx", "-g", "daemon off;"], check=True)
    except Exception as e:
        print(f"Error starting Nginx: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    generate_test_files()
    start_nginx()
