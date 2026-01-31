#include "ui/capra_ui.h"

#include <QApplication>
#include <QLocale>
#include <QTranslator>

#if defined(WITH_ROS2) && defined(WITH_PCL_VIS)
#include <QVTKOpenGLNativeWidget>
#endif

int main(int argc, char *argv[])
{
    // Initialize ROS 2 first (before QApplication)
    // This is needed for proper ROS 2 initialization
    
    QApplication a(argc, argv);
    
#if defined(WITH_ROS2) && defined(WITH_PCL_VIS)
    // Needed for VTK rendering in Qt
    QSurfaceFormat::setDefaultFormat(QVTKOpenGLNativeWidget::defaultFormat());
#endif

    QTranslator translator;
    const QStringList uiLanguages = QLocale::system().uiLanguages();
    for (const QString &locale : uiLanguages) {
        const QString baseName = "CAPRA_UI_" + QLocale(locale).name();
        if (translator.load(":/i18n/" + baseName)) {
            a.installTranslator(&translator);
            break;
        }
    }
    
    CAPRA_UI w;
    w.show();
    
    // Initialize ROS 2 in the main window's context
    // You can call this from a menu action instead if preferred
    // w.getRosNode()->init(argc, argv);
    
    return a.exec();
}
