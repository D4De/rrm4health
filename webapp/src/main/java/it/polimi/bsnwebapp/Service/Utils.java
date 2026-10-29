package it.polimi.bsnwebapp.Service;

import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.ServerSocket;
import java.util.Enumeration;

/**
 * Utility class usata da vari componenti (RrmConnectionService, controller ecc.).
 */
public class Utils {
    public static final long RRM_START_APPLICATION_TIMEOUT_SECONDS = 70;
    public static final long RRM_STOP_APPLICATION_TIMEOUT_SECONDS = 30;

    /**
     * Prova a trovare il primo indirizzo IPv4 non-loopback sulla macchina.
     * Ritorna "127.0.0.1" se non viene trovato.
     */
    public static String getLocalIp() {
        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces.hasMoreElements()) {
                NetworkInterface ni = interfaces.nextElement();
                if (!ni.isUp() || ni.isLoopback()) {
                    continue;
                }
                Enumeration<InetAddress> addrs = ni.getInetAddresses();
                while (addrs.hasMoreElements()) {
                    InetAddress addr = addrs.nextElement();
                    if (!addr.isLoopbackAddress() && addr.getHostAddress().indexOf(':')<0) {
                        return addr.getHostAddress();
                    }
                }
            }
        } catch (Exception e) {
            // ignore
        }
        return "127.0.0.1";
    }

    /**
     * Restituisce una porta libera sul localhost, o 0 in caso di errore.
     */
    public static int getFreePort() {
        try (ServerSocket socket = new ServerSocket(0)) {
            return socket.getLocalPort();
        } catch (Exception e) {
            return 0;
        }
    }
}
