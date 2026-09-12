using System;
using System.Diagnostics;
using System.IO;
using System.Net.Sockets;
using System.Threading;

namespace HermesOSLauncher
{
    /// <summary>
    /// Double-click launcher: starts the Hermes OS backend (uvicorn, :8010),
    /// frontend (Next.js dev server, :3010) and ComfyUI (:8188) if they
    /// aren't already running, waits for all three to answer, then opens
    /// the Cockpit in the default browser. Skips starting anything already
    /// up — running it twice does not spawn duplicate servers.
    ///
    /// Each server runs with no console window (CreateNoWindow, no shell) so
    /// there is nothing on the desktop an operator could close by mistake —
    /// the whole point of running this from a permanent launcher instead of
    /// three terminals kept open by hand. Output still goes somewhere: each
    /// process is redirected to its own file under data\logs\, because a
    /// hidden process that fails silently is worse than a visible one.
    /// </summary>
    internal static class Program
    {
        private const string RepoRoot = @"C:\Users\emeri\Hermes_OS-main";
        private const string FrontendDir = RepoRoot + @"\frontend";
        private const string ComfyUIDir = @"C:\AI\Apps\ComfyUI-ROCm\comfyui-rocm-091926";
        private const string LogDir = RepoRoot + @"\data\logs";
        private const int BackendPort = 8010;
        private const int FrontendPort = 3010;
        private const int ComfyUIPort = 8188;
        private const string CockpitUrl = "http://localhost:3010";

        private static void Main()
        {
            Console.Title = "Hermes OS - Launcher";
            Console.WriteLine("=== Hermes OS Launcher ===");
            Console.WriteLine();

            Directory.CreateDirectory(LogDir);

            EnsureBackend();
            EnsureFrontend();
            EnsureComfyUI();

            Console.WriteLine();
            Console.WriteLine("Ouverture du Cockpit dans le navigateur...");
            try
            {
                Process.Start(new ProcessStartInfo(CockpitUrl) { UseShellExecute = true });
            }
            catch (Exception ex)
            {
                Console.WriteLine("Impossible d'ouvrir le navigateur automatiquement : " + ex.Message);
                Console.WriteLine("Ouvrez manuellement : " + CockpitUrl);
            }

            Console.WriteLine();
            Console.WriteLine("Termine. Cette fenetre peut etre fermee ; les serveurs continuent de tourner");
            Console.WriteLine("en arriere-plan, sans fenetre visible. Journaux : " + LogDir);
            Console.WriteLine();
            Console.WriteLine("Appuyez sur une touche pour fermer cette fenetre...");
            try
            {
                Console.ReadKey();
            }
            catch (InvalidOperationException)
            {
                // No real console attached (e.g. launched from a script) —
                // nothing left to wait for.
            }
        }

        /// <summary>
        /// Starts a command hidden, with stdout/stderr appended to a log
        /// file, and detached from this launcher: closing or crashing the
        /// launcher must not take the server down with it, which a directly
        /// redirected child process (pipes owned by this process) would risk.
        /// Routing through "cmd /c ... >> log 2>&1" keeps the redirection
        /// entirely inside the child's own process tree.
        /// </summary>
        private static void StartHidden(string workingDirectory, string command, string logName)
        {
            string logPath = Path.Combine(LogDir, logName);
            var psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c " + command + " >> \"" + logPath + "\" 2>&1",
                WorkingDirectory = workingDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
            };
            Process.Start(psi);
        }

        private static void EnsureBackend()
        {
            if (IsPortOpen(BackendPort))
            {
                Console.WriteLine("Backend deja actif sur le port " + BackendPort + ".");
                return;
            }

            Console.WriteLine("Demarrage du backend (port " + BackendPort + ", arriere-plan)...");
            StartHidden(
                RepoRoot,
                ".venv\\Scripts\\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port " + BackendPort,
                "launcher-backend.log");

            WaitForPort(BackendPort, 90, "backend");
        }

        private static void EnsureFrontend()
        {
            if (IsPortOpen(FrontendPort))
            {
                Console.WriteLine("Frontend deja actif sur le port " + FrontendPort + ".");
                return;
            }

            Console.WriteLine("Demarrage du frontend (port " + FrontendPort + ", arriere-plan)...");
            StartHidden(
                FrontendDir,
                "npm run dev -- --port " + FrontendPort,
                "launcher-frontend.log");

            WaitForPort(FrontendPort, 60, "frontend");
        }

        private static void EnsureComfyUI()
        {
            if (IsPortOpen(ComfyUIPort))
            {
                Console.WriteLine("ComfyUI deja actif sur le port " + ComfyUIPort + ".");
                return;
            }

            if (!Directory.Exists(ComfyUIDir))
            {
                Console.WriteLine("ComfyUI introuvable dans " + ComfyUIDir + " - demarrage ignore.");
                return;
            }

            Console.WriteLine("Demarrage de ComfyUI (port " + ComfyUIPort + ", arriere-plan)...");
            // Le .bat existant porte toute la config ROCm (rocm-sdk init,
            // detection d'architecture GPU, caches Triton/TunableOp) : on
            // l'appelle tel quel plutot que de dupliquer cette logique ici.
            // "comfyui-rocm.bat" without a path segment fails cmd's command
            // lookup under Process.Start even with WorkingDirectory set
            // (reproduced directly: `dir comfyui-rocm.bat` finds it from the
            // same start info, but running it bare does not) — ".\" makes
            // it an explicit relative path instead of a bare command name.
            StartHidden(
                ComfyUIDir,
                ".\\comfyui-rocm.bat",
                "launcher-comfyui.log");

            WaitForPort(ComfyUIPort, 120, "ComfyUI");
        }

        private static void WaitForPort(int port, int timeoutSeconds, string label)
        {
            Console.Write("Attente du " + label + " ");
            var started = DateTime.UtcNow;
            while ((DateTime.UtcNow - started).TotalSeconds < timeoutSeconds)
            {
                if (IsPortOpen(port))
                {
                    Console.WriteLine(" OK (" + (int)(DateTime.UtcNow - started).TotalSeconds + "s)");
                    return;
                }
                Console.Write(".");
                Thread.Sleep(1500);
            }
            Console.WriteLine();
            Console.WriteLine(
                "Le " + label + " n'a pas repondu apres " + timeoutSeconds +
                "s. Verifiez la fenetre correspondante pour une erreur ; le navigateur va quand meme s'ouvrir.");
        }

        private static bool IsPortOpen(int port)
        {
            try
            {
                using (var client = new TcpClient())
                {
                    var result = client.BeginConnect("127.0.0.1", port, null, null);
                    var connected = result.AsyncWaitHandle.WaitOne(TimeSpan.FromMilliseconds(500));
                    if (connected && client.Connected)
                    {
                        client.EndConnect(result);
                        return true;
                    }
                    return false;
                }
            }
            catch
            {
                return false;
            }
        }
    }
}
