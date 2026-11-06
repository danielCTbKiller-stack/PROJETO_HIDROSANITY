// GeoLogic Water.exe (executável mestre, na pasta acima de Projeto WaterConnect) - abre o hub
// (Projeto WaterConnect\hub.py) sem janela de console.
//
// O hub só precisa do PySide6: usa o Python da pasta do hub (.venv), se houver, ou o do GPREDIAL
// (Projeto WaterConnect\GPREDIAL\.venv).
// Como roda direto o hub.py, não precisa recompilar quando o hub muda. Erros vão para geologic_water_erros.log.
//
// Compilar (o compilador vem com o Windows) - ou rode compilar_lancador.bat:
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /out:"..\..\GeoLogic Water.exe"
//       /win32icon:geologic.ico /reference:System.Windows.Forms.dll GeoLogicWater.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

class GeoLogicWater
{
    [STAThread]
    static void Main(string[] args)
    {
        string hub = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Projeto WaterConnect");
        string log = Path.Combine(hub, "geologic_water_erros.log");
        string pythonw = null;
        foreach (string c in new[] { Path.Combine(hub, ".venv", "Scripts", "pythonw.exe"),
                                     Path.Combine(hub, "GPREDIAL", ".venv", "Scripts", "pythonw.exe") })
            if (File.Exists(c)) { pythonw = c; break; }
        if (pythonw == null)
        {
            MessageBox.Show("Não encontrei um Python com PySide6 para o hub.\n\n" +
                            "Instale o GPREDIAL (Projeto WaterConnect\\GPREDIAL\\instalar.bat) ou crie um .venv nesta pasta com o PySide6.",
                            "GeoLogic Water", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        var info = new ProcessStartInfo(pythonw, "\"" + Path.Combine(hub, "hub.py") + "\"")
        {
            WorkingDirectory = hub,
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
                MessageBox.Show("O GeoLogic Water fechou com erro.\n\nDetalhes em:\n" + log, "GeoLogic Water",
                                MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
        catch (Exception e)
        {
            MessageBox.Show("Não foi possível abrir o GeoLogic Water:\n" + e.Message, "GeoLogic Water",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
