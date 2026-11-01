// GWATER.exe - lançador do programa GWATER (REV 0.2.0).
//
// O programa é Python (app\gwater_app.py) e usa as bibliotecas do QGIS. Este lançador:
//   1. acha o QGIS: o da própria pasta (runtime\qgis, versão portátil para pen drive) ou o instalado
//      (4.x de preferência, senão 3.x; GWATER.ini pode apontar outro);
//   2. confere o Python do motor (.venv) e oferece criar se faltar (preparar_ambiente.bat);
//   3. abre o programa pelo python-qgis do QGIS, sem janela de console.
// O arquivo a abrir (duplo clique num .qgz/.gpkg ou arrastar sobre o .exe) vai na variável GWATER_ABRIR:
// o .bat do QGIS não aceita argumentos com espaço no caminho.
//
// Compilar (o compilador vem com o Windows):
//   C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /target:winexe /out:..\GWATER.exe
//       /win32icon:gwater.ico /reference:System.Windows.Forms.dll GWATER.cs
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

class GWATER
{
    static string AcharQgis(string raiz)
    {
        // versão portátil: o QGIS vai junto, na pasta runtime\qgis (roda de qualquer pasta ou pen drive)
        string portatil = Bat(Path.Combine(raiz, "runtime", "qgis"));
        if (portatil != null) return portatil;
        // GWATER.ini: linha "qgis=C:\caminho\do\QGIS" força uma instalação
        string ini = Path.Combine(raiz, "GWATER.ini");
        if (File.Exists(ini))
        {
            foreach (string linha in File.ReadAllLines(ini))
            {
                string l = linha.Trim();
                if (l.StartsWith("qgis=", StringComparison.OrdinalIgnoreCase))
                {
                    string b = Bat(l.Substring(5).Trim());
                    if (b != null) return b;
                }
            }
        }
        var pastas = new System.Collections.Generic.List<string>();
        foreach (string pf in new[] { Environment.GetEnvironmentVariable("ProgramFiles"), @"C:\Program Files" })
        {
            if (pf != null && Directory.Exists(pf))
                pastas.AddRange(Directory.GetDirectories(pf, "QGIS *"));
        }
        pastas.Add(@"C:\OSGeo4W");
        pastas.Add(@"C:\OSGeo4W64");
        // QGIS 4 primeiro (Qt6), depois o mais novo do 3
        foreach (string p in pastas.Distinct().OrderByDescending(Versao))
        {
            string b = Bat(p);
            if (b != null) return b;
        }
        return null;
    }

    static Version Versao(string pasta)
    {
        string nome = Path.GetFileName(pasta.TrimEnd('\\')).Replace("QGIS ", "");
        Version v;
        return Version.TryParse(nome, out v) ? v : new Version(0, 0);
    }

    static string Bat(string pasta)
    {
        foreach (string nome in new[] { "python-qgis.bat", "python-qgis-ltr.bat" })
        {
            string b = Path.Combine(pasta, "bin", nome);
            if (File.Exists(b)) return b;
        }
        return null;
    }

    [STAThread]
    static int Main(string[] args)
    {
        string raiz = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        string app = Path.Combine(raiz, "app");
        if (!File.Exists(Path.Combine(app, "gwater_app.py")))
        {
            MessageBox.Show("Não achei app\\gwater_app.py ao lado do GWATER.exe.\n\nO GWATER.exe precisa ficar na pasta "
                            + "do programa (REV 0.2.0), junto das pastas app, motor e painel.", "GWATER",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string bat = AcharQgis(raiz);
        if (bat == null)
        {
            MessageBox.Show("O GWATER usa as bibliotecas do QGIS (mapa e edição), e não achei o QGIS neste computador.\n\n"
                            + "Instale o QGIS 4.2 (ou o 3.44 LTR) de https://qgis.org e abra o GWATER de novo.\n"
                            + "Se o QGIS estiver em outra pasta, crie GWATER.ini ao lado do GWATER.exe com a linha:\n"
                            + "qgis=C:\\caminho\\do\\QGIS", "GWATER", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 2;
        }
        string venv = Path.Combine(raiz, ".venv", "Scripts", "python.exe");
        string pyPortatil = Path.Combine(raiz, "runtime", "python", "python.exe");
        string preparar = Path.Combine(raiz, "preparar_ambiente.bat");
        bool ehPortatil = File.Exists(pyPortatil) && Directory.Exists(Path.Combine(raiz, "runtime", "qgis"));
        if (!File.Exists(venv) && !File.Exists(pyPortatil) && File.Exists(preparar))
        {
            var r = MessageBox.Show("Falta preparar o motor de cálculo (Python com o EPANET), o que é feito uma vez só e "
                                    + "precisa de internet.\n\nPreparar agora?", "GWATER", MessageBoxButtons.YesNo,
                                    MessageBoxIcon.Question);
            if (r == DialogResult.Yes)
            {
                var prep = Process.Start(new ProcessStartInfo(preparar) { WorkingDirectory = raiz, UseShellExecute = true });
                prep.WaitForExit();
            }
        }
        var psi = new ProcessStartInfo("cmd.exe", "/c \"\"" + bat + "\" gwater_app.py\"");
        psi.WorkingDirectory = app;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        psi.EnvironmentVariables["GWATER_RAIZ"] = raiz;
        if (ehPortatil)  // configurações, perfil do QGIS e logins ficam na pasta (vão junto no pen drive)
        {
            string dados = Path.Combine(raiz, "dados");
            Directory.CreateDirectory(dados);
            psi.EnvironmentVariables["GWATER_DADOS"] = dados;
        }
        if (args.Length > 0) psi.EnvironmentVariables["GWATER_ABRIR"] = Path.GetFullPath(args[0]);
        try
        {
            Process.Start(psi);
        }
        catch (Exception e)
        {
            MessageBox.Show("Não consegui abrir o GWATER: " + e.Message, "GWATER", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 3;
        }
        return 0;
    }
}
