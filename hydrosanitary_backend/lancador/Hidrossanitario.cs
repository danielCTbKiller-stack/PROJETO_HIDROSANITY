// Hidrossanitario.exe - lançador do programa (mesma ideia do GWATER.exe).
//
// O programa é Python (gui\app.py). Este lançador:
//   1. confere o ambiente Python (.venv) e oferece criar se faltar (instalar.bat);
//   2. abre o programa pelo pythonw.exe do .venv, sem janela de console;
//   3. repassa o arquivo a abrir (duplo clique num .hsp/.dxf/.ifc ou arrastar sobre o .exe).
// Como roda direto o código-fonte, não precisa recompilar quando o programa muda.
// Erros de inicialização vão para hidrossanitario_erros.log.
//
// Compilar (o compilador vem com o Windows) - ou rode compilar_lancador.bat:
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /out:..\Hidrossanitario.exe
//       /win32icon:hidrossanitario.ico /reference:System.Windows.Forms.dll Hidrossanitario.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class Hidrossanitario
{
    [STAThread]
    static void Main(string[] args)
    {
        string raiz = AppDomain.CurrentDomain.BaseDirectory;
        string pythonw = Path.Combine(raiz, ".venv", "Scripts", "pythonw.exe");
        string log = Path.Combine(raiz, "hidrossanitario_erros.log");

        if (!File.Exists(pythonw))
        {
            string instalar = Path.Combine(raiz, "instalar.bat");
            DialogResult r = MessageBox.Show(
                "O ambiente do programa ainda não foi instalado nesta pasta.\n\n" +
                "Instalar agora? (precisa do Python 3.10+ e de internet; leva alguns minutos)",
                "Hidrossanitário", MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (r != DialogResult.Yes) return;
            if (!File.Exists(instalar))
            {
                MessageBox.Show("instalar.bat não encontrado em " + raiz, "Hidrossanitário",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            Process p = Process.Start(new ProcessStartInfo("cmd.exe", "/c \"\"" + instalar + "\"\"")
                                      { WorkingDirectory = raiz, UseShellExecute = false });
            p.WaitForExit();
            if (!File.Exists(pythonw))
            {
                MessageBox.Show("A instalação não terminou. Veja as mensagens da janela do instalar.bat.",
                                "Hidrossanitário", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
        }

        string arquivo = args.Length > 0 && File.Exists(args[0]) ? " \"" + Path.GetFullPath(args[0]) + "\"" : "";
        var info = new ProcessStartInfo(pythonw, "-m gui.app" + arquivo)
        {
            WorkingDirectory = raiz,
            UseShellExecute = false,
            RedirectStandardError = true,
        };
        info.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        try
        {
            Process proc = Process.Start(info);
            string erros = proc.StandardError.ReadToEnd();
            proc.WaitForExit();
            if (proc.ExitCode != 0)
            {
                File.WriteAllText(log, DateTime.Now + "\r\n" + erros);
                MessageBox.Show("O programa fechou com erro.\n\nDetalhes em:\n" + log, "Hidrossanitário",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        catch (Exception e)
        {
            MessageBox.Show("Não foi possível abrir o programa:\n" + e.Message, "Hidrossanitário",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
