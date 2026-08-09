using System;
using System.Diagnostics;
using System.Net.Sockets;
using System.Threading;

namespace HermesOSLauncher
{
    /// <summary>
    /// Double-click launcher: starts the Hermes OS backend (uvicorn, :8010)
    /// and frontend (Next.js dev server, :3010) if they aren't already
    /// running, waits for both to answer, then opens the Cockpit in the
    /// default browser. Skips starting anything already up — running it
    /// twice does not spawn duplicate servers.
    /// </summary>
    internal static class Program
    {
        private const string RepoRoot = @"C:\Users\emeri\Hermes_OS-main";
        private const string FrontendDir = RepoRoot + @"\frontend";
        private const int BackendPort = 8010;
        private const int FrontendPort = 3010;
        private const string CockpitUrl = "http://localhost:3010";

        private static void Main()
        {
            Console.Title = "Hermes OS - Launcher";
            Console.WriteLine("=== Hermes OS Launcher ===");
            Console.WriteLine();

            EnsureBackend();
            EnsureFrontend();

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
            Console.WriteLine("dans leurs propres fenetres.");
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

        private static void EnsureBackend()
        {
            if (IsPortOpen(BackendPort))
            {
                Console.WriteLine("Backend deja actif sur le port " + BackendPort + ".");
                return;
            }

            Console.WriteLine("Demarrage du backend (port " + BackendPort + ")...");
            var psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/k title Hermes OS - Backend && python -m uvicorn backend.main:app --host 127.0.0.1 --port " + BackendPort,
                WorkingDirectory = RepoRoot,
                UseShellExecute = true,
            };
            Process.Start(psi);

            WaitForPort(BackendPort, 90, "backend");
        }

        private static void EnsureFrontend()
        {
            if (IsPortOpen(FrontendPort))
            {
                Console.WriteLine("Frontend deja actif sur le port " + FrontendPort + ".");
                return;
            }

            Console.WriteLine("Demarrage du frontend (port " + FrontendPort + ")...");
            var psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/k title Hermes OS - Frontend && npm run dev -- --port " + FrontendPort,
                WorkingDirectory = FrontendDir,
                UseShellExecute = true,
            };
            Process.Start(psi);

            WaitForPort(FrontendPort, 60, "frontend");
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
